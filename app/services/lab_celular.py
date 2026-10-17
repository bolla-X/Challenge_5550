"""Laboratório "celular em área de risco" (M9, MISSÃO 4): regra pura, DESLIGADA por padrão.

O detector de pessoa do projeto é o YOLOv8n do COCO (`PERSON_MODEL_PATH`), e o
COCO tem a classe `cell phone` (id 67; Lin et al., "Microsoft COCO", Tabela 2:
https://arxiv.org/pdf/1405.0312). Ela hoje é descartada de propósito: o detector
roda com `classes=[0]` (`MonitorService.person_detector`). Para a regra ver o
celular alguém precisa abrir o filtro para `[0, 67]` — só com
`LAB_CELULAR_ATIVO=true`. Evidência e motivo de ser laboratório: ver a seção
"M9 — laboratório" de docs/NEXT2026/CHANGELOG.md.

Este módulo não toca em câmera, em modelo nem em banco. Entra um quadro de
detecções, sai uma lista de `RuleAlert`; com `ativo=False` sai SEMPRE lista
vazia, sem olhar as detecções (nada muda quando desligado).

Decisões:

- o celular conta quando o CENTRO da caixa está dentro da área de risco da
  câmera (mesmo ponto-em-polígono do matcher de EPI, normalizado pelo quadro);
- só vira alerta com uma pessoa associada: o centro do celular tem de estar
  dentro da caixa de uma pessoa. Celular sozinho (em cima de uma bancada) não é
  "uso"; a pessoa escolhida é a de menor caixa que o contém (a mais próxima);
- "uso" aqui é PRESENÇA do celular junto de uma pessoa na área, não atenção
  nem ligação: o sistema não sabe se alguém olha a tela. O texto do alerta diz
  "em uso" como a MISSÃO pediu; a limitação vai na documentação do laboratório;
- um alerta por pessoa (chave `celular_em_area:celular:<pessoa>`), como os
  outros alertas por pessoa; várias detecções na mesma pessoa contam uma vez, a
  de maior confiança.

"Pessoa N" é rótulo de rastreio, nunca identidade (GLOSSARIO.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.services.risk_rules import RuleAlert
from app.vision.person_compliance_matcher import PersonComplianceMatcher
from app.vision.schemas import BoundingBox, Detection

CLASSE_COCO_CELULAR = 67
ROTULO_COCO_CELULAR = "cell phone"
REGRA = "celular_em_area"
RECURSO = "celular"
SEVERIDADE = "medium"
LIMIAR_PADRAO = 0.5


def e_celular(det: Detection) -> bool:
    """`cell phone` do COCO. Só o rótulo: o id 67 de outro modelo (ex.: Vyra) não é celular."""
    return det.label == ROTULO_COCO_CELULAR or det.category == ROTULO_COCO_CELULAR


def _e_pessoa(det: Detection) -> bool:
    return det.label == "person" or det.category == "person"


def _contem(caixa: BoundingBox, ponto: tuple[int, int]) -> bool:
    return caixa.x1 <= ponto[0] <= caixa.x2 and caixa.y1 <= ponto[1] <= caixa.y2


def _pessoa_do_celular(celular: Detection, pessoas: Sequence[Detection]) -> Detection | None:
    """A pessoa de menor caixa que contém o centro do celular, ou None."""
    centro = celular.box.center
    donas = [p for p in pessoas if _contem(p.box, centro)]
    return min(donas, key=lambda p: p.box.area) if donas else None


def _rotulo_da_pessoa(pessoa: Detection, indice: int) -> str:
    return f"Pessoa {pessoa.track_id if pessoa.track_id is not None else indice}"


def avaliar_celular(
    deteccoes: Sequence[Detection],
    *,
    ativo: bool,
    limiar: float,
    poligono: Sequence[tuple[float, float]] | None,
    forma_do_quadro: tuple[int, ...] | None,
) -> list[RuleAlert]:
    """Alertas `celular_em_area` do quadro; `[]` se desligado, sem área de risco ou sem quadro.

    `deteccoes` traz pessoas E celulares do mesmo quadro (o worker junta as
    saídas dos detectores). `poligono` é a área de risco normalizada (0–1) e
    `forma_do_quadro` o `frame.shape` (altura, largura, ...).
    """
    if not ativo or not poligono or not forma_do_quadro:
        return []
    altura, largura = forma_do_quadro[:2]
    pessoas = [d for d in deteccoes if _e_pessoa(d)]
    por_pessoa: dict[int, tuple[Detection, Detection]] = {}
    for celular in (d for d in deteccoes if e_celular(d) and d.confidence >= limiar):
        cx, cy = celular.box.center
        if not PersonComplianceMatcher._point_in_polygon((cx / max(1, largura), cy / max(1, altura)), list(poligono)):
            continue
        dona = _pessoa_do_celular(celular, pessoas)
        if dona is None:
            continue
        indice = pessoas.index(dona)
        atual = por_pessoa.get(indice)
        if atual is None or celular.confidence > atual[1].confidence:
            por_pessoa[indice] = (dona, celular)
    return [_alerta(dona, celular, indice, largura, altura) for indice, (dona, celular) in sorted(por_pessoa.items())]


def _alerta(dona: Detection, celular: Detection, indice: int, largura: int, altura: int) -> RuleAlert:
    rotulo = _rotulo_da_pessoa(dona, indice)
    cx, cy = celular.box.center
    metadata: dict[str, Any] = {
        # Mesmo formato do matcher de EPI: o alerta do celular e o de EPI da mesma pessoa compartilham o rastreio.
        "person_id": f"person_{dona.track_id if dona.track_id is not None else indice}",
        "person_label": rotulo,
        "person_box": dona.box.to_dict(),
        "celular_box": celular.box.to_dict(),
        "celular_confianca": round(float(celular.confidence), 4),
        "point": {"x": round(cx / max(1, largura), 4), "y": round(cy / max(1, altura), 4)},
        "laboratorio": True,
    }
    return RuleAlert(
        rule=REGRA,
        severity=SEVERIDADE,
        message=f"Celular em uso na área de risco · {rotulo}",
        feature=RECURSO,
        metadata=metadata,
    )
