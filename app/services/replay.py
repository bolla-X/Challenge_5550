"""Replay de incidente: buffer circular em memória + clipe com pré e pós-evento.

O snapshot do alerta é UM quadro — mostra que havia alguém sem capacete, não
o que aconteceu antes. Aqui cada câmera guarda os últimos `segundos` em JPEG
de baixa resolução (com o desfoque de privacidade já aplicado) e o overlay de
cada quadro. Quando um alerta nasce, o clipe vai de `antes_s` antes até
`depois_s` depois, e só é montado quando o "depois" de fato aconteceu.

Padrão do Frigate (`frigate/record/maintainer.py`: mantém o que cruza
[início − pre_capture, fim + post_capture]), mas em memória e em JPEG, porque
aqui não há ffmpeg gravando segmentos.

Garantias:
- memória LIMITADA por quadros (`maxlen`) e por bytes (`max_bytes`): estourou,
  sai o mais velho;
- NUNCA fabrica quadro: o clipe tem exatamente os quadros gravados, cada um
  com o instante de captura; buraco (câmera travou) aparece como buraco.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2


@dataclass
class QuadroDeReplay:
    ts_ms: float
    jpeg: bytes
    overlay: dict[str, Any] | None
    escala: float


class BufferDeReplay:
    def __init__(self, *, segundos: float = 8.0, fps_max: float = 10.0, lado: int = 480,
                 qualidade: int = 60, max_bytes: int = 4 * 1024 * 1024) -> None:
        self.segundos = segundos
        self.intervalo_ms = 1000.0 / max(0.5, fps_max)
        self.lado = lado
        self.qualidade = qualidade
        self.max_bytes = max_bytes
        self._quadros: deque[QuadroDeReplay] = deque(maxlen=int(segundos * fps_max) + 2)
        self._bytes = 0
        self._ultimo_ms = 0.0
        self._lock = threading.Lock()

    def deve_gravar(self, ts_ms: float) -> bool:
        return ts_ms - self._ultimo_ms >= self.intervalo_ms * 0.95

    def gravar(self, quadro, ts_ms: float, overlay: dict[str, Any] | None) -> None:
        altura, largura = quadro.shape[:2]
        escala = min(1.0, self.lado / max(altura, largura))
        pequeno = cv2.resize(quadro, (int(largura * escala), int(altura * escala)), interpolation=cv2.INTER_AREA) \
            if escala < 1.0 else quadro
        ok, buffer = cv2.imencode(".jpg", pequeno, [int(cv2.IMWRITE_JPEG_QUALITY), self.qualidade])
        if not ok:
            return
        jpeg = buffer.tobytes()
        with self._lock:
            if len(self._quadros) == self._quadros.maxlen:
                self._bytes -= len(self._quadros[0].jpeg)
            self._quadros.append(QuadroDeReplay(ts_ms, jpeg, overlay, escala))
            self._bytes += len(jpeg)
            while self._bytes > self.max_bytes and len(self._quadros) > 1:
                self._bytes -= len(self._quadros.popleft().jpeg)
            # Janela por TEMPO além do maxlen: com FPS baixo o maxlen guardaria
            # mais que `segundos` de história.
            while self._quadros and ts_ms - self._quadros[0].ts_ms > self.segundos * 1000.0:
                self._bytes -= len(self._quadros.popleft().jpeg)
            self._ultimo_ms = ts_ms

    def entre(self, inicio_ms: float, fim_ms: float) -> list[QuadroDeReplay]:
        with self._lock:
            return [q for q in self._quadros if inicio_ms <= q.ts_ms <= fim_ms]

    def estado(self) -> dict[str, Any]:
        with self._lock:
            return {"quadros": len(self._quadros), "bytes": self._bytes,
                    "janela_s": round((self._quadros[-1].ts_ms - self._quadros[0].ts_ms) / 1000.0, 1) if self._quadros else 0.0}

    def limpar(self) -> None:
        with self._lock:
            self._quadros.clear()
            self._bytes = 0
            self._ultimo_ms = 0.0


@dataclass
class ClipePendente:
    alert_id: int
    t0_ms: float
    fim_ms: float
    inicio_ms: float
    alerta: dict[str, Any]


def gravar_clipe(diretorio: Path, pendente: ClipePendente, quadros: list[QuadroDeReplay], camera_id: int | None) -> dict[str, Any]:
    """Escreve os quadros e o índice do clipe. Roda no thread do GravadorAssincrono."""
    pasta = diretorio / f"alert_{pendente.alert_id}"
    pasta.mkdir(parents=True, exist_ok=True)
    indice = []
    for i, q in enumerate(quadros):
        (pasta / f"{i:04d}.jpg").write_bytes(q.jpeg)
        indice.append({"i": i, "ts_ms": q.ts_ms, "rel_ms": round(q.ts_ms - pendente.t0_ms, 1),
                       "overlay": q.overlay, "escala": q.escala})
    meta = pendente.alerta.get("metadata") or {}
    clipe = {
        "alert_id": pendente.alert_id,
        "camera_id": camera_id,
        "t0_ms": pendente.t0_ms,
        "janela_ms": [round(pendente.inicio_ms - pendente.t0_ms), round(pendente.fim_ms - pendente.t0_ms)],
        "quadros": indice,
        "total": len(indice),
        "pessoa": meta.get("person_label") or meta.get("person_id") or meta.get("subject"),
        "regra": pendente.alerta.get("rule"),
        "mensagem": pendente.alerta.get("message"),
        "severidade": pendente.alerta.get("severity"),
        # As evidências que SUSTENTARAM a decisão, como estavam no alerta.
        "evidencias": {k: meta.get(k) for k in ("confirmation_frames", "present_labels", "supported_ppe", "person_box", "method")
                       if meta.get(k) is not None},
        "gerado_em": time.time(),
    }
    (pasta / "clip.json").write_text(json.dumps(clipe, ensure_ascii=False), encoding="utf-8")
    return clipe
