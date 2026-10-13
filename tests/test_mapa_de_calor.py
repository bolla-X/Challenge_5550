"""Mapa de calor de risco (F7): acumula onde houve violação e esquece com o tempo."""

from __future__ import annotations

from app.services.mapa_de_calor import MapaDeCalor, pes_em_risco


def test_soma_na_celula_dos_pes_e_normaliza():
    mapa = MapaDeCalor(colunas=10, linhas=10)
    mapa.somar([(0.05, 0.95), (0.05, 0.95), (0.55, 0.55)], agora=0.0)
    dados = mapa.exportar(agora=0.0)
    assert dados["grade"][9][0] == 1.0, "célula mais quente normalizada em 1"
    assert dados["grade"][5][5] == 0.5
    assert dados["eventos"] == 3


def test_meia_vida_esquece_o_passado():
    mapa = MapaDeCalor(colunas=4, linhas=4, meia_vida_s=10.0)
    mapa.somar([(0.1, 0.1)], agora=0.0)
    assert abs(mapa.exportar(agora=10.0)["maximo"] - 0.5) < 1e-3


def test_pes_so_de_quem_esta_em_violacao_ou_na_zona():
    estado = {"people": [
        {"box": {"x1": 0, "y1": 0, "x2": 100, "y2": 300}, "ppe": {"helmet": {"status": "missing"}}, "risk_area": {"status": "outside"}},
        {"box": {"x1": 200, "y1": 0, "x2": 300, "y2": 300}, "ppe": {"helmet": {"status": "ok"}}, "risk_area": {"status": "outside"}},
        {"box": {"x1": 400, "y1": 0, "x2": 500, "y2": 540}, "ppe": {}, "risk_area": {"status": "inside"}},
    ]}
    pontos = pes_em_risco(estado, (540, 960, 3))
    assert pontos == [(50 / 960, 300 / 540), (450 / 960, 1.0)]
