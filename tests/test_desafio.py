"""G2: pontuação igual para a pessoa e para a IA, contra o gabarito curado."""

from __future__ import annotations

import pytest
from app.services.desafio import RODADAS, Desafio, pontuar

PESSOAS = [
    {"caixa": (0, 0, 100, 300), "sem_capacete": True},
    {"caixa": (200, 0, 300, 300), "sem_capacete": False},
    {"caixa": (400, 0, 500, 300), "sem_capacete": True},
    {"caixa": (900, 0, 960, 540), "sem_capacete": None},
]


def test_acertos_erros_e_perdidos():
    r = pontuar(PESSOAS, [(50, 100), (50, 120), (250, 100), (700, 100), (930, 200)])
    # 2 cliques na mesma pessoa contam 1; com capacete e chão são erros; neutra não conta.
    assert r == {"acertos": 1, "erros": 2, "perdidos": 1, "alvos": 2}


def test_rodada_pegadinha_sem_ninguem_para_apontar():
    canteiro = next(r for r in RODADAS if r["id"] == "canteiro-94")
    assert pontuar(canteiro["pessoas"], []) == {"acertos": 0, "erros": 0, "perdidos": 0, "alvos": 0}
    assert pontuar(canteiro["pessoas"], [(260, 200)])["erros"] == 1


def test_gabarito_tem_caixas_validas_no_960x540():
    for r in RODADAS:
        for p in r["pessoas"]:
            x1, y1, x2, y2 = p["caixa"]
            assert 0 <= x1 < x2 <= 960 and 0 <= y1 < y2 <= 540, (r["id"], p)


def _Det(label, box):
    from app.vision.schemas import BoundingBox, Detection

    return Detection(label=label, confidence=0.9, box=BoundingBox(*box), category="person" if label == "person" else "ppe")


class _Detector:
    def __init__(self, deteccoes):
        self.deteccoes = deteccoes

    def detect(self, _quadro):
        return self.deteccoes


def test_ia_responde_pelo_mesmo_casamento_dos_alertas(monkeypatch):
    import app.services.desafio as mod
    import numpy as np

    class _Cap:
        def set(self, *_):
            pass

        def read(self):
            return True, np.zeros((540, 960, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(mod.cv2, "VideoCapture", lambda _caminho: _Cap())
    # A IA vê 2 pessoas na multidão; capacete só na segunda → aponta a primeira.
    pessoas = [_Det("person", (0, 115, 82, 448)), _Det("person", (232, 72, 372, 508))]
    epis = [_Det("helmet", (270, 75, 330, 120))]
    d = Desafio({"multidao": "x", "bench": "y"}, detector=_Detector(epis), person_detector=_Detector(pessoas))
    r = d.responder("multidao-168", [(40, 300)], tempo_ms=4200)
    assert r["humano"]["acertos"] == 1 and r["humano"]["perdidos"] == 4
    assert r["ia"]["acertos"] == 1 and r["ia"]["perdidos"] == 4 and r["ia"]["erros"] == 0
    assert len(d.quadro("multidao-168", 0)) > 100
    with pytest.raises(LookupError):
        d.quadro("multidao-168", 99)
