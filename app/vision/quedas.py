"""Queda pela classe `Fall-Detected` do Vyra, atribuída a uma pessoa rastreada (F2).

A queda por pose (`RuleEngine._is_fallen`, orientação do tronco) depende de o
detector de pessoa ver quem está no chão — e, na fixture de queda, ele NÃO vê:
nos quadros com a pessoa caída, a maior fração da caixa de queda dentro de
alguma caixa de pessoa foi 0,00–0,18 (sondagem em docs/NEXT2026/CHANGELOG.md, F2).
O Vyra tem uma classe própria para isso. Regras daqui:

1. a caixa de queda pertence à pessoa rastreada que mais a contém
   (`containment_in` ≥ `LIMIAR_SOBREPOSICAO`);
2. se ninguém a contém, a própria caixa entra no rastreador COMO PESSOA (uma
   pessoa caída é uma pessoa) e ganha um ID de rastreio — é ele que aparece no
   alerta. ID de rastreio não é identidade.
"""

from __future__ import annotations

from typing import Any

from app.vision.schemas import BoundingBox, Detection

LIMIAR_SOBREPOSICAO = 0.3
ROTULO_QUEDA = "fall_detected"


def e_queda(det: Detection) -> bool:
    return det.label == ROTULO_QUEDA


def pessoas_com_quedas(pessoas: list[Detection], deteccoes: list[Detection]) -> list[Detection]:
    """As pessoas detectadas + uma "pessoa" para cada queda que nenhuma delas contém."""
    extras = [
        Detection(label="person", confidence=q.confidence, box=q.box, category="person")
        for q in deteccoes
        if e_queda(q) and not any(q.box.containment_in(p.box) >= LIMIAR_SOBREPOSICAO for p in pessoas)
    ]
    return list(pessoas) + extras


def _caixa(valor: Any) -> BoundingBox | None:
    if isinstance(valor, BoundingBox):
        return valor
    if isinstance(valor, dict) and all(k in valor for k in ("x1", "y1", "x2", "y2")):
        return BoundingBox(int(valor["x1"]), int(valor["y1"]), int(valor["x2"]), int(valor["y2"]))
    return None


def atribuir_quedas(deteccoes: list[Detection], pessoas: list[dict[str, Any]]) -> list[tuple[Detection, dict[str, Any] | None]]:
    """Cada queda com a pessoa (estado do matcher) que mais a contém, ou None."""
    saida = []
    for queda in (d for d in deteccoes if e_queda(d)):
        melhor, fracao = None, 0.0
        for pessoa in pessoas:
            caixa = _caixa(pessoa.get("box"))
            if caixa is None:
                continue
            f = queda.box.containment_in(caixa)
            if f > fracao:
                melhor, fracao = pessoa, f
        saida.append((queda, melhor if fracao >= LIMIAR_SOBREPOSICAO else None))
    return saida
