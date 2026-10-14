"""Re-associação de ID depois do rastreador (MISSÃO 2, P0.2)."""

from __future__ import annotations

from app.vision.person_tracker import PersonTracker
from app.vision.reassociacao import RastreadorComReassociacao, ReassociadorDeIds
from app.vision.schemas import BoundingBox, Detection


class _Relogio:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def pessoa(x: int, cru: int, y: int = 100, largura: int = 60) -> Detection:
    return Detection(label="person", confidence=0.9, box=BoundingBox(x, y, x + largura, y + 160)).with_track_id(cru)


def ids(deteccoes) -> list[int]:
    return [d.track_id for d in deteccoes]


def test_track_novo_perto_de_onde_outro_sumiu_herda_o_id():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    assert ids(r.aplicar([pessoa(100, cru=1)])) == [1]
    relogio.t = 0.5
    assert ids(r.aplicar([])) == []  # sumiu (oclusão)
    relogio.t = 1.2
    # Rastreador deu ID cru 7; voltou 50 px ao lado (< 1,5 × 60 px).
    assert ids(r.aplicar([pessoa(150, cru=7)])) == [1]
    assert r.herancas == 1


def test_longe_demais_nao_herda():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    r.aplicar([pessoa(100, cru=1)])
    relogio.t = 0.5
    r.aplicar([])
    relogio.t = 1.0
    # 100 px > 1,5 × 60 = 90 px.
    assert ids(r.aplicar([pessoa(200, cru=2)])) == [2]


def test_depois_da_janela_de_2_s_nao_herda():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    r.aplicar([pessoa(100, cru=1)])
    relogio.t = 0.5
    r.aplicar([])
    relogio.t = 2.6  # sumiu em 0,5 s; 2,1 s depois
    assert ids(r.aplicar([pessoa(110, cru=2)])) == [2]


def test_quem_esta_em_cena_nunca_e_herdado():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    r.aplicar([pessoa(100, cru=1)])
    relogio.t = 0.3
    # Pessoa 1 continua em cena e aparece alguém colado nela: ID novo.
    assert ids(r.aplicar([pessoa(100, cru=1), pessoa(120, cru=2)])) == [1, 2]


def test_dois_sumidos_cada_novo_herda_o_mais_proximo():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    r.aplicar([pessoa(100, cru=1), pessoa(400, cru=2)])
    relogio.t = 0.4
    r.aplicar([])
    relogio.t = 0.8
    saida = r.aplicar([pessoa(410, cru=8), pessoa(110, cru=9)])
    por_x = {d.box.x1: d.track_id for d in saida}
    assert por_x == {110: 1, 410: 2}


def test_id_cru_antigo_que_volta_nao_duplica_o_herdado():
    relogio = _Relogio()
    r = ReassociadorDeIds(relogio=relogio)
    r.aplicar([pessoa(100, cru=1)])
    relogio.t = 0.3
    r.aplicar([])
    relogio.t = 0.6
    assert ids(r.aplicar([pessoa(120, cru=5)])) == [1]
    relogio.t = 0.9
    # O rastreador "reencontrou" o cru 1 em outro lugar: não pode virar 1 de novo.
    saida = ids(r.aplicar([pessoa(120, cru=5), pessoa(600, cru=1)]))
    assert sorted(saida) == [1, 2]


def test_reset_recomeca_a_numeracao():
    r = ReassociadorDeIds()
    r.aplicar([pessoa(100, cru=10)])
    r.reset()
    assert ids(r.aplicar([pessoa(100, cru=3)])) == [1]


def test_com_o_rastreador_iou_uma_oclusao_curta_mantem_o_id():
    """Ponta a ponta com o PersonTracker: a pessoa pula de lugar (IoU 0) e volta perto."""
    relogio = _Relogio()
    rastreador = RastreadorComReassociacao(PersonTracker(max_age=0), ReassociadorDeIds(relogio=relogio))

    def det(x):
        return Detection(label="person", confidence=0.9, box=BoundingBox(x, 100, x + 60, 260))

    primeiro = ids(rastreador.update([det(100)]))
    relogio.t = 0.4
    rastreador.update([])  # max_age=0: o rastreador cru esquece a pessoa
    relogio.t = 0.8
    depois = ids(rastreador.update([det(170)]))  # cru novo; 70 px < 90 px
    assert primeiro == depois == [1]
