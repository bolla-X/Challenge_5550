"""Avaliacao por PESSOA do pipeline de EPI (Sprint 4).

Por que por pessoa, e nao mAP: o operador nao recebe "caixa de capacete com
IoU 0,62"; recebe "Pessoa 3 sem capacete". O erro que importa e o do ALERTA:

- alerta sobre quem esta de EPI (falso positivo) gasta a confianca do operador;
- violacao sem alerta (falso negativo) e o acidente que o sistema existe para
  evitar.

O ground truth vem de um dataset anotado no formato YOLO que tem, alem das
classes positivas (``helmet``, ``vest``...), classes NEGATIVAS explicitas
(``no_helmet``, ``none`` = torso sem colete...). Isso permite tres estados por
EPI, e o terceiro e o que as tres cenas da Sprint 3 nao conseguiam medir:

- ``presente``: anotado de EPI;
- ``ausente``: anotado SEM o EPI (violacao);
- ``nao_visivel``: nao anotado de nenhum dos dois jeitos (oculto, fora do
  quadro, pequeno demais). Aqui nao ha verdade, entao nao entra na conta de
  acerto — mas os alertas disparados nesses casos sao contados a parte.

Este modulo e puro: nao carrega modelo, nao abre imagem. Quem roda o modelo e
``scripts/avaliar_dataset.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.vision.schemas import BoundingBox

PRESENTE = "presente"
AUSENTE = "ausente"
NAO_VISIVEL = "nao_visivel"

# EPIs avaliados, com o nome interno do projeto (o mesmo de PPE_KEYS).
EPIS_AVALIADOS = ("helmet", "vest", "gloves", "glasses", "safety_shoe")

# Nome da classe no dataset -> (epi, positivo?). Cobre o Construction-PPE da
# Ultralytics. "none" e o nome que o dataset da ao torso SEM colete.
CLASSES_DATASET: dict[str, tuple[str, bool]] = {
    "helmet": ("helmet", True),
    "no_helmet": ("helmet", False),
    "vest": ("vest", True),
    "none": ("vest", False),
    "gloves": ("gloves", True),
    "no_gloves": ("gloves", False),
    "goggles": ("glasses", True),
    "no_goggle": ("glasses", False),
    "boots": ("safety_shoe", True),
    "no_boots": ("safety_shoe", False),
}
CLASSE_PESSOA = "Person"

# Fracao minima da caixa do EPI dentro da caixa da pessoa para associar.
_CONTENCAO_MINIMA = 0.5


def ler_rotulos_yolo(arquivo: Path, nomes: list[str], *, largura: int, altura: int) -> list[tuple[str, BoundingBox]]:
    """Le um .txt YOLO (classe cx cy w h, normalizados) e devolve caixas em pixels."""
    caixas: list[tuple[str, BoundingBox]] = []
    for linha in Path(arquivo).read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) < 5:
            continue
        classe = int(partes[0])
        cx, cy, w, h = (float(v) for v in partes[1:5])
        x1 = round((cx - w / 2) * largura)
        y1 = round((cy - h / 2) * altura)
        x2 = round((cx + w / 2) * largura)
        y2 = round((cy + h / 2) * altura)
        caixas.append((nomes[classe], BoundingBox(x1, y1, x2, y2)))
    return caixas


@dataclass
class PessoaAnotada:
    caixa: BoundingBox
    status: dict[str, str]


def ground_truth_por_pessoa(caixas: list[tuple[str, BoundingBox]]) -> list[PessoaAnotada]:
    """Associa cada caixa de EPI anotada a UMA pessoa anotada e deriva o status.

    Associacao: a pessoa que contem a maior fracao da caixa do EPI (minimo 50%);
    empate desfeito pela distancia entre centros. Negativa vence positiva: uma
    luva e uma mao nua na mesma pessoa e violacao.
    """
    pessoas = [caixa for nome, caixa in caixas if nome == CLASSE_PESSOA]
    achados: list[dict[str, set[bool]]] = [{epi: set() for epi in EPIS_AVALIADOS} for _ in pessoas]
    for nome, caixa in caixas:
        if nome not in CLASSES_DATASET or not pessoas:
            continue
        epi, positivo = CLASSES_DATASET[nome]
        melhor = _pessoa_que_contem(caixa, pessoas)
        if melhor is not None:
            achados[melhor][epi].add(positivo)

    resultado: list[PessoaAnotada] = []
    for caixa, marcas in zip(pessoas, achados, strict=True):
        status = {}
        for epi in EPIS_AVALIADOS:
            if False in marcas[epi]:
                status[epi] = AUSENTE
            elif True in marcas[epi]:
                status[epi] = PRESENTE
            else:
                status[epi] = NAO_VISIVEL
        resultado.append(PessoaAnotada(caixa=caixa, status=status))
    return resultado


def _pessoa_que_contem(caixa: BoundingBox, pessoas: list[BoundingBox]) -> int | None:
    cx, cy = caixa.center
    candidatos = []
    for indice, pessoa in enumerate(pessoas):
        contencao = caixa.containment_in(pessoa)
        if contencao >= _CONTENCAO_MINIMA:
            px, py = pessoa.center
            candidatos.append((-contencao, (cx - px) ** 2 + (cy - py) ** 2, indice))
    if not candidatos:
        return None
    return min(candidatos)[2]


def casar_pessoas(gt: list[BoundingBox], previstas: list[BoundingBox], *, iou_minimo: float = 0.5) -> dict[int, int]:
    """Casamento guloso e exclusivo por IoU: {indice_gt: indice_previsto}."""
    pares = []
    for i, caixa_gt in enumerate(gt):
        for j, caixa_prev in enumerate(previstas):
            iou = caixa_gt.iou(caixa_prev)
            if iou >= iou_minimo:
                pares.append((iou, i, j))
    pares.sort(reverse=True)
    usados_gt: set[int] = set()
    usados_prev: set[int] = set()
    casamento: dict[int, int] = {}
    for _iou, i, j in pares:
        if i in usados_gt or j in usados_prev:
            continue
        casamento[i] = j
        usados_gt.add(i)
        usados_prev.add(j)
    return casamento


@dataclass
class Matriz:
    """Matriz de confusao do ALERTA de um EPI. Positivo = pessoa sem o EPI."""

    vp: int = 0
    fp: int = 0
    fn: int = 0
    vn: int = 0
    # Alerta disparado sobre pessoa cujo EPI nao da para julgar na anotacao.
    sem_verdade_com_alerta: int = 0
    sem_verdade_sem_alerta: int = 0
    exemplos: dict[str, list[str]] = field(default_factory=lambda: {"fp": [], "fn": [], "vp": []})

    @property
    def precisao(self) -> float | None:
        return self.vp / (self.vp + self.fp) if (self.vp + self.fp) else None

    @property
    def revocacao(self) -> float | None:
        return self.vp / (self.vp + self.fn) if (self.vp + self.fn) else None

    @property
    def f1(self) -> float | None:
        p, r = self.precisao, self.revocacao
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def acuracia(self) -> float | None:
        total = self.vp + self.fp + self.fn + self.vn
        return (self.vp + self.vn) / total if total else None

    def to_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 4)

        return {
            "vp": self.vp,
            "fp": self.fp,
            "fn": self.fn,
            "vn": self.vn,
            "suporte_ausente": self.vp + self.fn,
            "suporte_presente": self.fp + self.vn,
            "precisao": r(self.precisao),
            "revocacao": r(self.revocacao),
            "f1": r(self.f1),
            "acuracia": r(self.acuracia),
            "sem_verdade_com_alerta": self.sem_verdade_com_alerta,
            "sem_verdade_sem_alerta": self.sem_verdade_sem_alerta,
        }


def contar(matriz: Matriz, *, verdade: str, alerta: bool, exemplo: str | None = None) -> None:
    if verdade == NAO_VISIVEL:
        if alerta:
            matriz.sem_verdade_com_alerta += 1
        else:
            matriz.sem_verdade_sem_alerta += 1
        return
    violacao = verdade == AUSENTE
    if violacao and alerta:
        matriz.vp += 1
        chave = "vp"
    elif not violacao and alerta:
        matriz.fp += 1
        chave = "fp"
    elif violacao and not alerta:
        matriz.fn += 1
        chave = "fn"
    else:
        matriz.vn += 1
        chave = None
    if exemplo and chave and len(matriz.exemplos[chave]) < 12:
        matriz.exemplos[chave].append(exemplo)
