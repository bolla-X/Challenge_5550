"""Aprendizado ativo (G9): fila de recortes duvidosos para a equipe rotular.

Detecções de EPI com confiança no meio da faixa (padrão 0,25–0,5) são as que
mais ensinam a um próximo treino. Elas viram recortes do quadro PÚBLICO — o
mesmo que vai para a tela, com rosto desfocado (F4) — numa fila limitada no
disco. O técnico confirma (→) ou rejeita (←) e a fila exporta um zip no
formato de dataset YOLO (images/ + labels/ + data.yaml + README com a origem e a
licença). Nada de treino dentro do app.

Privacidade × rótulo: o desfoque do vídeo cobre a cabeça inteira — e com ela o
capacete (primeira versão: recortes de capacete saíam pixelados, inúteis). O
recorte agora desfoca só olhos e nariz (keypoints da pose); sem keypoints de
alguma pessoa, não recorta. Com a privacidade ligada, óculos, máscara e
protetor auricular — que só se vê no rosto — não são coletados.

Limites, para não virar custo nem acúmulo:
- no máximo um recorte por câmera a cada `intervalo_s`;
- `limite` recortes pendentes (a fila não cresce além disso);
- a confiança mínima efetiva é a do detector (`YOLO_CONFIDENCE`): abaixo dela
  as caixas nem chegam aqui.
"""

from __future__ import annotations

import io
import json
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import cv2

from app.vision.person_compliance_matcher import PPE_KEYS

MARGEM = 0.3  # recorte = caixa + 30 % de cada lado, para ter contexto
LADO_MAX = 320
LADO_MIN = 96


class FilaDeRotulos:
    def __init__(self, pasta: Path, *, limite: int = 300, conf_min: float = 0.25, conf_max: float = 0.5,
                 intervalo_s: float = 5.0) -> None:
        self.pasta = Path(pasta)
        self.limite = limite
        self.conf_min, self.conf_max = conf_min, conf_max
        self.intervalo_s = intervalo_s
        self._ultimo_por_camera: dict[Any, float] = {}
        self._lock = threading.Lock()
        for sub in ("fila", "confirmados", "rejeitados"):
            (self.pasta / sub).mkdir(parents=True, exist_ok=True)

    # ---- coleta (thread da câmera) ----------------------------------------
    def candidato(self, detections, *, excluir: frozenset[str] = frozenset()) -> Any | None:
        """A detecção de EPI mais duvidosa (mais perto do meio da faixa)."""
        na_faixa = [d for d in detections if d.label in PPE_KEYS and d.label not in excluir
                    and self.conf_min <= d.confidence < self.conf_max]
        return min(na_faixa, key=lambda d: abs(d.confidence - (self.conf_min + self.conf_max) / 2), default=None)

    def talvez_coletar(self, camera_id, quadro_publico, detections, agora: float | None = None, *,
                       excluir: frozenset[str] = frozenset()) -> str | None:
        """`quadro_publico` pode ser o quadro ou uma função que o produz: o
        desfoque só é pago quando há candidato e o intervalo da câmera venceu."""
        agora = time.monotonic() if agora is None else agora
        if agora - self._ultimo_por_camera.get(camera_id, -1e9) < self.intervalo_s:
            return None
        det = self.candidato(detections, excluir=excluir)
        if det is None:
            return None
        if callable(quadro_publico):
            quadro_publico = quadro_publico()
        if quadro_publico is None:
            return None
        with self._lock:
            if len(list((self.pasta / "fila").glob("*.json"))) >= self.limite:
                return None
            self._ultimo_por_camera[camera_id] = agora
            recorte, caixa = _recortar(quadro_publico, det.box)
            if recorte is None:
                return None
            ident = uuid.uuid4().hex[:12]
            ok, jpeg = cv2.imencode(".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return None
            (self.pasta / "fila" / f"{ident}.jpg").write_bytes(jpeg.tobytes())
            meta = {"id": ident, "classe": det.label, "confianca": round(float(det.confidence), 3),
                    "camera_id": camera_id, "caixa_no_recorte": caixa, "criado_em": time.time()}
            (self.pasta / "fila" / f"{ident}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            return ident

    # ---- revisão (rota /rotular) ------------------------------------------
    def proximo(self) -> dict[str, Any] | None:
        with self._lock:
            itens = sorted((self.pasta / "fila").glob("*.json"), key=lambda p: p.stat().st_mtime)
            return json.loads(itens[0].read_text(encoding="utf-8")) if itens else None

    def imagem(self, ident: str) -> Path | None:
        if not ident.isalnum():
            return None
        for sub in ("fila", "confirmados", "rejeitados"):
            caminho = self.pasta / sub / f"{ident}.jpg"
            if caminho.exists():
                return caminho
        return None

    def decidir(self, ident: str, decisao: str) -> dict[str, Any]:
        if decisao not in ("confirmar", "rejeitar") or not ident.isalnum():
            raise ValueError("decisão inválida")
        destino = self.pasta / ("confirmados" if decisao == "confirmar" else "rejeitados")
        with self._lock:
            meta_p = self.pasta / "fila" / f"{ident}.json"
            if not meta_p.exists():
                raise LookupError("recorte não está na fila")
            meta = json.loads(meta_p.read_text(encoding="utf-8")) | {"decisao": decisao, "decidido_em": time.time()}
            (self.pasta / "fila" / f"{ident}.jpg").replace(destino / f"{ident}.jpg")
            (destino / f"{ident}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            meta_p.unlink()
        return meta

    def contagem(self) -> dict[str, int]:
        return {sub: len(list((self.pasta / sub).glob("*.json"))) for sub in ("fila", "confirmados", "rejeitados")}

    def exportar_zip(self) -> bytes:
        """Dataset YOLO só com os CONFIRMADOS (o rejeitado não diz qual é a classe certa)."""
        buffer = io.BytesIO()
        with self._lock, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            n = 0
            for meta_p in sorted((self.pasta / "confirmados").glob("*.json")):
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                img = meta_p.with_suffix(".jpg")
                if not img.exists() or meta["classe"] not in PPE_KEYS:
                    continue
                x, y, w, h = meta["caixa_no_recorte"]
                z.write(img, f"images/train/{meta['id']}.jpg")
                z.writestr(f"labels/train/{meta['id']}.txt", f"{PPE_KEYS.index(meta['classe'])} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
                n += 1
            nomes = "\n".join(f"  {i}: {k}" for i, k in enumerate(PPE_KEYS))
            z.writestr("data.yaml", f"path: .\ntrain: images/train\nval: images/train\nnames:\n{nomes}\n")
            z.writestr("README.md", _README.format(n=n))
        return buffer.getvalue()


def _recortar(quadro, box) -> tuple[Any, list[float] | None]:
    """Recorte com margem e a caixa YOLO (cx, cy, w, h normalizados) dentro dele."""
    altura, largura = quadro.shape[:2]
    bw, bh = box.x2 - box.x1, box.y2 - box.y1
    if bw <= 2 or bh <= 2:
        return None, None
    # Margem de contexto, com um lado mínimo: capacete a distância tem ~20 px.
    meia_l = max(bw * (0.5 + MARGEM), LADO_MIN / 2)
    meia_a = max(bh * (0.5 + MARGEM), LADO_MIN / 2)
    cx, cy = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
    x1, y1 = max(0, int(cx - meia_l)), max(0, int(cy - meia_a))
    x2, y2 = min(largura, int(cx + meia_l)), min(altura, int(cy + meia_a))
    recorte = quadro[y1:y2, x1:x2]
    rw, rh = x2 - x1, y2 - y1
    caixa = [((box.x1 + box.x2) / 2 - x1) / rw, ((box.y1 + box.y2) / 2 - y1) / rh, bw / rw, bh / rh]
    escala = min(1.0, LADO_MAX / max(rw, rh))
    if escala < 1.0:
        recorte = cv2.resize(recorte, (max(1, int(rw * escala)), max(1, int(rh * escala))), interpolation=cv2.INTER_AREA)
    return recorte, [round(min(1.0, max(0.0, v)), 6) for v in caixa]


_README = """# Recortes rotulados pela equipe — VisionEPI (aprendizado ativo)

{n} recorte(s) confirmados por um técnico. Formato YOLO (Ultralytics):
`images/train/*.jpg`, `labels/train/*.txt` (classe cx cy w h, normalizados) e
`data.yaml` com os nomes das classes.

Origem e cuidados:

- Cada imagem é um RECORTE do quadro público do VisionEPI, com rosto
  desfocado (modo privacidade). Não há nome, identidade nem ID de pessoa.
- Só entram detecções em que o modelo estava em dúvida (confiança média) e
  que um técnico CONFIRMOU. Os rejeitados não entram: não dizem a classe certa.
- `val` aponta para o mesmo conjunto: separe uma validação antes de treinar.

Licença: os recortes herdam a licença da gravação de origem. Nas gravações de
demonstração do projeto: CC BY-SA 4.0 (canteiro, Acabashi), CC0 (multidão,
Taurus Media Technik) e domínio público (queda, EYE Filmmuseum) — ver
docs/NEXT2026/ATRIBUICOES.md. Imagens de câmeras de uma empresa pertencem a ela
e não devem sair sem autorização.
"""
