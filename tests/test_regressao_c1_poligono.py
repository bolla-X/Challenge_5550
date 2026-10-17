"""Regressão C1 (bug hunt da MISSÃO 4): ponto-em-polígono errado em aresta inclinada.

`max(yj - yi, 1e-12)` troca o sinal do denominador quando a aresta "sobe"
(yj < yi): uma pessoa FORA de uma zona em trapézio saía "dentro" — alerta falso de
área de risco e incidente na zona errada. Retângulos escapavam por acaso.
"""

from __future__ import annotations

import pytest
from app.services.aproximacao import ponto_no_poligono
from app.services.risk_rules import RuleEngine
from app.services.simulador import dentro
from app.vision.person_compliance_matcher import PersonComplianceMatcher
from app.vision.schemas import BoundingBox

TRAPEZIO = [(0.2, 0.2), (0.8, 0.2), (0.9, 0.8), (0.1, 0.8)]
CASOS = [((0.95, 0.5), False), ((0.86, 0.5), False), ((0.84, 0.5), True), ((0.5, 0.5), True), ((0.12, 0.3), False),
         ((0.17, 0.5), True)]


@pytest.mark.parametrize(("ponto", "esperado"), CASOS)
def test_todas_as_copias_concordam_com_a_referencia(ponto, esperado):
    assert ponto_no_poligono(ponto, TRAPEZIO) is esperado
    assert RuleEngine._point_in_polygon(ponto, TRAPEZIO) is esperado
    assert dentro(ponto, tuple(TRAPEZIO)) is esperado


def test_matcher_diz_fora_para_pessoa_a_direita_do_trapezio():
    caixa = BoundingBox(int(0.95 * 960) - 20, int(0.5 * 540) - 40, int(0.95 * 960) + 20, int(0.5 * 540) + 40)
    status = PersonComplianceMatcher._risk_status(PersonComplianceMatcher, caixa, TRAPEZIO, (540, 960, 3))
    assert status["status"] == "outside", status
