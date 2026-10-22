"""Área de detecção por câmera (MISSÃO 7): o único lugar do quadro onde o sistema procura pessoas.

A câmera do NEXT mostra a plateia, mas só o palco interessa. Com a área configurada:

1. a inferência (EPI, pessoa e pose) roda só no retângulo envolvente do polígono, com 5 % do quadro de margem
   nos lados e embaixo e 30 % em cima (`MARGEM_TOPO`): quem tem os pés logo abaixo da borda de cima tem o corpo
   ACIMA dela, e com só 5 % o modelo veria a pessoa sem cabeça (alerta falso de "sem capacete");
2. as caixas voltam para as coordenadas do quadro inteiro (somar o canto do recorte); o letterbox do modelo já
   é desfeito pelo ultralytics, que devolve `Boxes.xyxy` no tamanho da imagem que recebeu — aqui, o recorte.
   A doc oficial (https://docs.ultralytics.com/modes/predict/#boxes) não diz o tamanho de `xyxy` por escrito;
   a fonte é o código da 8.3.40: `ultralytics/models/yolo/detect/predict.py:39`
   (`ops.scale_boxes(img.shape[2:], pred[:, :4], orig_img.shape)`), coberto por teste com `ops.scale_boxes`.
   Lote com recortes de formas diferentes usa letterbox quadrado (mesma página, seção "Fixed shape vs minimum
   rectangle"; na 8.3.40, `engine/predictor.py:155-158`) — muda o preenchimento, não o mapeamento de volta;
3. pessoa (e queda, que vira pessoa antes do rastreador) só fica se o ponto dos pés — centro da base da caixa —
   cair dentro do polígono; EPI só fica se estiver associado a uma pessoa mantida (mesma fração de contenção do
   filtro EPI↔pessoa do worker, `PPE_PERSON_OVERLAP_MIN`).

Sem área (`None`), nada muda: o quadro vai inteiro ao modelo e as detecções saem como entraram — é o
comportamento de antes da MISSÃO 7, coberto por teste de identidade.

A saúde visual (M1) não passa por aqui: obstrução e câmera movida olham o quadro inteiro.

Evidências (snapshot, clipe, recorte de rótulo) saem com a parte de fora escurecida e desfocada
(`aplicar(..., desfocar=True)`); miniaturas e vídeo anotado, só escurecida; o vídeo ao vivo escurece no navegador,
a partir do polígono no overlay. Nos três, a caixa de quem foi MANTIDO fica nítida mesmo com a cabeça fora do
polígono: a evidência de uma violação não pode sair borrada justamente na cabeça.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import Any, Callable

import cv2
import numpy as np

from app.vision.schemas import BoundingBox, Detection, PoseResult

MARGEM = 0.05
# Acima do polígono: o corpo de quem tem os pés perto da borda de cima. 30 % do quadro cobre uma pessoa em pé
# de até ~30 % da altura do quadro (as câmeras da demo: 15–35 %). Desvio registrado da spec (que pede 5 %).
MARGEM_TOPO = 0.30
# Caixa de pessoa mantida, nítida na imagem: 10 % maior em cada lado (capacete e mãos na borda da caixa).
FOLGA_DA_CAIXA = 0.10
# Menor área aceita, em fração do quadro: abaixo de 1 % o recorte não cabe uma pessoa inteira em nenhuma das
# câmeras da demo (960×540: 1 % ≈ 72×72 px).
AREA_MINIMA = 0.01
MAX_PONTOS = 64
# Fora da área: brilho multiplicado por este fator (vídeo ao vivo, miniaturas e evidências).
ESCURECIMENTO = 0.35
# Evidência: reduz a 1/16 e volta ao tamanho — borrão forte, sem rosto legível.
REDUCAO_DO_DESFOQUE = 16

Ponto = tuple[float, float]

logger = logging.getLogger(__name__)


def _numero(valor: Any) -> float:
    # Só número de JSON: texto ("0.5") e booleano não; inteiro gigante dá OverflowError no float().
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("Cada ponto da área de detecção precisa de x e y numéricos.")
    try:
        numero = float(valor)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Cada ponto da área de detecção precisa de x e y numéricos.") from exc
    if not math.isfinite(numero):
        raise ValueError("Cada ponto da área de detecção precisa de x e y numéricos.")
    return numero


def area_do_poligono(poligono: list[Ponto]) -> float:
    """Área (fórmula do laço), em fração do quadro quando os pontos são normalizados."""
    soma = 0.0
    for i, (x1, y1) in enumerate(poligono):
        x2, y2 = poligono[(i + 1) % len(poligono)]
        soma += x1 * y2 - x2 * y1
    return abs(soma) / 2.0


def _orientacao(a: Ponto, b: Ponto, c: Ponto) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segmentos_cruzam(p1: Ponto, p2: Ponto, p3: Ponto, p4: Ponto) -> bool:
    """Cruzamento próprio (as pontas não contam): é o que faz o polígono se dobrar sobre si."""
    d1, d2 = _orientacao(p3, p4, p1), _orientacao(p3, p4, p2)
    d3, d4 = _orientacao(p1, p2, p3), _orientacao(p1, p2, p4)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def validar_poligono(raw: Any) -> list[Ponto]:
    """Lista de {x,y} ou [x,y] → pontos 0..1. Levanta ValueError com a mensagem para a tela.

    Diferente da área de risco, ponto fora de 0–1 é recusado (não é grudado na borda): a área decide o que o
    sistema deixa de ver, então salvar outra coisa que não a desenhada seria pior que recusar.
    """
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError("A área de detecção precisa de pelo menos 3 pontos.")
    if len(raw) > MAX_PONTOS:
        raise ValueError(f"A área de detecção aceita no máximo {MAX_PONTOS} pontos.")
    poligono: list[Ponto] = []
    for ponto in raw:
        if isinstance(ponto, dict):
            x, y = ponto.get("x"), ponto.get("y")
        elif isinstance(ponto, (list, tuple)) and len(ponto) == 2:
            x, y = ponto
        else:
            raise ValueError("Cada ponto da área de detecção precisa de x e y.")
        xf, yf = _numero(x), _numero(y)
        if not (0.0 <= xf <= 1.0 and 0.0 <= yf <= 1.0):
            raise ValueError("Os pontos da área de detecção precisam ficar dentro do quadro (de 0 a 1).")
        poligono.append((round(xf, 4), round(yf, 4)))
    if len(set(poligono)) != len(poligono):
        raise ValueError("A área de detecção tem pontos repetidos.")
    n = len(poligono)
    for i in range(n):
        for j in range(i + 1, n):
            # Arestas vizinhas compartilham um vértice; não são cruzamento.
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segmentos_cruzam(poligono[i], poligono[(i + 1) % n], poligono[j], poligono[(j + 1) % n]):
                raise ValueError("A área de detecção não pode cruzar a si mesma.")
    if area_do_poligono(poligono) < AREA_MINIMA:
        raise ValueError("A área de detecção é pequena demais: desenhe ao menos 1 % do quadro.")
    return poligono


def ponto_no_poligono(x: float, y: float, poligono: list[Ponto]) -> bool:
    """Raio horizontal (paridade de cruzamentos): vale para polígono côncavo."""
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def ponto_dos_pes(caixa: BoundingBox) -> tuple[float, float]:
    """Centro da base da caixa, em pixels: o mesmo ponto que a aproximação (F3) e a planta usam."""
    return ((caixa.x1 + caixa.x2) / 2.0, float(caixa.y2))


def _e_pessoa(det: Detection) -> bool:
    from app.vision.quedas import e_queda

    return det.label == "person" or det.category == "person" or e_queda(det)


def deslocar(det: Detection, dx: int, dy: int) -> Detection:
    """A detecção feita no recorte, nas coordenadas do quadro inteiro (caixa e esqueleto)."""
    if dx == 0 and dy == 0:
        return det
    caixa = BoundingBox(det.box.x1 + dx, det.box.y1 + dy, det.box.x2 + dx, det.box.y2 + dy)
    pontos = det.keypoints
    if pontos is not None:
        # (0, 0) é o "não visto" do ultralytics (ponto com confiança < 0,5) e de quem lê o esqueleto
        # (pose_da_deteccao, privacidade, sinais_por_id): deslocá-lo criaria uma junta falsa no canto do recorte.
        pontos = tuple((x + dx, y + dy, c) if (x or y) else (x, y, c) for x, y, c in pontos)
    return replace(det, box=caixa, keypoints=pontos)


def remapear_pose(pose: PoseResult, deslocamento: tuple[int, int], forma_do_recorte, forma_do_quadro) -> PoseResult:
    """Pose estimada no recorte (landmarks normalizados NO RECORTE) → normalizados no quadro inteiro."""
    dx, dy = deslocamento
    alt_r, larg_r = forma_do_recorte[:2]
    alt_q, larg_q = forma_do_quadro[:2]
    pontos = [replace(lm, x=(dx + lm.x * larg_r) / max(1, larg_q), y=(dy + lm.y * alt_r) / max(1, alt_q))
              for lm in pose.landmarks]
    return replace(pose, landmarks=pontos)


def pes_da_pose(pose: PoseResult) -> tuple[float, float] | None:
    """Ponto dos pés de uma pose sem caixa: média dos tornozelos visíveis; sem eles, o ponto mais baixo."""
    tornozelos = [lm for lm in pose.landmarks if lm.name in ("left_ankle", "right_ankle") and lm.visibility >= 0.3]
    if tornozelos:
        return (sum(lm.x for lm in tornozelos) / len(tornozelos), sum(lm.y for lm in tornozelos) / len(tornozelos))
    if not pose.landmarks:
        return None
    mais_baixo = max(pose.landmarks, key=lambda lm: lm.y)
    return (mais_baixo.x, mais_baixo.y)


class AreaDeDeteccao:
    """Imutável: trocar a área troca o objeto. Quem recortou um quadro devolve com a MESMA área, mesmo que o
    técnico salve outra no meio da inferência."""

    def __init__(self, poligono: list[Ponto] | None) -> None:
        self.poligono: list[Ponto] | None = [(float(x), float(y)) for x, y in poligono] if poligono else None
        self._mascaras: dict[tuple[int, int], np.ndarray] = {}

    @property
    def ativa(self) -> bool:
        return self.poligono is not None

    def para_api(self) -> list[dict[str, float]] | None:
        return [{"x": x, "y": y} for x, y in self.poligono] if self.poligono else None

    def para_banco(self) -> list[list[float]] | None:
        return [[x, y] for x, y in self.poligono] if self.poligono else None

    # ------------------------------------------------------------ recorte --
    def retangulo(self, largura: int, altura: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) em pixels: envolvente do polígono + 5 % do quadro em cada lado, dentro do quadro."""
        if not self.poligono:
            return 0, 0, largura, altura
        xs = [x for x, _ in self.poligono]
        ys = [y for _, y in self.poligono]
        x0 = max(0, int(math.floor((min(xs) - MARGEM) * largura)))
        y0 = max(0, int(math.floor((min(ys) - MARGEM_TOPO) * altura)))
        x1 = min(largura, int(math.ceil((max(xs) + MARGEM) * largura)))
        y1 = min(altura, int(math.ceil((max(ys) + MARGEM) * altura)))
        return x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)

    def recortar(self, frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int] | None]:
        """(o que vai ao modelo, deslocamento do recorte). Sem área: o próprio quadro e None."""
        if not self.poligono:
            return frame, None
        altura, largura = frame.shape[:2]
        x0, y0, x1, y1 = self.retangulo(largura, altura)
        # Fatia é vista do mesmo buffer (sem cópia); o ultralytics só lê.
        return frame[y0:y1, x0:x1], (x0, y0)

    # ----------------------------------------------------------- filtro --
    def mantem_pessoa(self, det: Detection, largura: int, altura: int) -> bool:
        if not self.poligono:
            return True
        px, py = ponto_dos_pes(det.box)
        return ponto_no_poligono(px / max(1, largura), py / max(1, altura), self.poligono)

    def mantem_pose(self, pose: PoseResult) -> bool:
        """Pose global (sem caixa de pessoa): mesmo critério, pelos pés da pose."""
        if not self.poligono:
            return True
        pes = pes_da_pose(pose)
        return pes is not None and ponto_no_poligono(pes[0], pes[1], self.poligono)

    def filtrar(self, deteccoes: list[Detection], pessoas: list[Detection], esqueletos: list[Detection] | None,
                largura: int, altura: int, sobreposicao_min: float) -> tuple[list, list, list | None]:
        """Pessoas pelo ponto dos pés; EPI só se contido numa pessoa mantida."""
        if not self.poligono:
            return deteccoes, pessoas, esqueletos
        pessoas = [p for p in pessoas if self.mantem_pessoa(p, largura, altura)]
        if esqueletos is not None:
            esqueletos = [e for e in esqueletos if self.mantem_pessoa(e, largura, altura)]
        pessoas_do_epi = [d for d in deteccoes if _e_pessoa(d) and self.mantem_pessoa(d, largura, altura)]
        referencias = [p.box for p in pessoas] + [p.box for p in pessoas_do_epi] + [e.box for e in esqueletos or []]
        mantidas = []
        for det in deteccoes:
            if _e_pessoa(det):
                if self.mantem_pessoa(det, largura, altura):
                    mantidas.append(det)
            elif any(det.box.containment_in(ref) >= sobreposicao_min for ref in referencias):
                mantidas.append(det)
        return mantidas, pessoas, esqueletos

    def devolver(self, bruto: tuple, deslocamento: tuple[int, int] | None, largura: int, altura: int,
                 sobreposicao_min: float) -> tuple[list, list, list | None]:
        """O resultado do modelo no recorte → quadro inteiro, já filtrado. Sem área: o próprio `bruto`."""
        deteccoes, pessoas, esqueletos = bruto
        if not self.poligono:
            return deteccoes, pessoas, esqueletos
        dx, dy = deslocamento or (0, 0)
        deteccoes = [deslocar(d, dx, dy) for d in deteccoes]
        pessoas = [deslocar(p, dx, dy) for p in pessoas]
        esqueletos = None if esqueletos is None else [deslocar(e, dx, dy) for e in esqueletos]
        return self.filtrar(deteccoes, pessoas, esqueletos, largura, altura, sobreposicao_min)

    def para_lote(self, frame: np.ndarray, sobreposicao_min: float) -> tuple[np.ndarray, Callable[[tuple], tuple] | None]:
        """Para o agendador em lote: (entrada do modelo, função que devolve o bruto ao quadro inteiro).

        Sem área: (o próprio quadro, None) — o agendador junta esses no mesmo lote, exatamente como antes.
        """
        if not self.poligono:
            return frame, None
        entrada, deslocamento = self.recortar(frame)
        altura, largura = frame.shape[:2]
        return entrada, lambda bruto: self.devolver(bruto, deslocamento, largura, altura, sobreposicao_min)

    # ----------------------------------------------------------- imagem --
    def mascara(self, altura: int, largura: int) -> np.ndarray:
        """255 dentro do polígono, 0 fora (uma por resolução, guardada)."""
        chave = (altura, largura)
        mascara = self._mascaras.get(chave)
        if mascara is None:
            mascara = np.zeros((altura, largura), dtype=np.uint8)
            pontos = np.array([[round(x * largura), round(y * altura)] for x, y in self.poligono or []], dtype=np.int32)
            if len(pontos) >= 3:
                cv2.fillPoly(mascara, [pontos], 255)
            self._mascaras[chave] = mascara
        return mascara

    def aplicar(self, frame: np.ndarray | None, *, desfocar: bool, caixas: list[BoundingBox] | tuple = ()) -> np.ndarray | None:
        """Cópia com o lado de fora escurecido (e desfocado, para evidência). Sem área: o próprio quadro.

        `caixas`: pessoas mantidas, que ficam nítidas inteiras (com folga) mesmo saindo do polígono.
        """
        if frame is None or not self.poligono:
            return frame
        altura, largura = frame.shape[:2]
        mascara = self.mascara(altura, largura)
        if caixas:
            mascara = mascara.copy()
            for c in caixas:
                fx, fy = (c.x2 - c.x1) * FOLGA_DA_CAIXA, (c.y2 - c.y1) * FOLGA_DA_CAIXA
                cv2.rectangle(mascara, (max(0, int(c.x1 - fx)), max(0, int(c.y1 - fy))),
                              (min(largura - 1, int(c.x2 + fx)), min(altura - 1, int(c.y2 + fy))), 255, -1)
        fora = frame
        if desfocar:
            pequeno = cv2.resize(frame, (max(1, largura // REDUCAO_DO_DESFOQUE), max(1, altura // REDUCAO_DO_DESFOQUE)),
                                 interpolation=cv2.INTER_AREA)
            fora = cv2.resize(pequeno, (largura, altura), interpolation=cv2.INTER_LINEAR)
        saida = cv2.convertScaleAbs(fora, alpha=ESCURECIMENTO, beta=0)
        cv2.copyTo(frame, mascara, saida)
        return saida


SEM_AREA = AreaDeDeteccao(None)


def do_banco(valor: Any) -> AreaDeDeteccao:
    """A coluna `Camera.area_deteccao` → área. Valor inválido no banco vira "sem área" (e não derruba o worker)."""
    if not valor:
        return SEM_AREA
    try:
        return AreaDeDeteccao(validar_poligono(valor))
    except ValueError as exc:
        logger.warning("area_deteccao_invalida_no_banco", extra={"motivo": str(exc)})
        return SEM_AREA


def caixas_de_pessoas(deteccoes) -> list[BoundingBox]:
    """As caixas que ficam nítidas na imagem: pessoas (e quedas) mantidas pela análise."""
    return [d.box for d in deteccoes or [] if _e_pessoa(d)]


def fora_da_area(poligono_de_risco: list[Ponto], area: AreaDeDeteccao, passos: int = 8) -> bool:
    """A área de risco tem parte fora da área de detecção? (vértices e pontos ao longo das arestas)."""
    if not area.poligono or len(poligono_de_risco) < 3:
        return False
    n = len(poligono_de_risco)
    for i in range(n):
        (x1, y1), (x2, y2) = poligono_de_risco[i], poligono_de_risco[(i + 1) % n]
        for k in range(passos):
            t = k / passos
            if not ponto_no_poligono(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, area.poligono):
                return True
    return False
