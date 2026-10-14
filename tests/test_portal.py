"""G1: Portal de Entrada — confirmado, faltando, ou não verificável neste enquadramento."""

from __future__ import annotations

from app.services.gate_service import (
    CONFIRMADO,
    FALTANDO,
    NAO_VERIFICAVEL,
    PortalState,
    avaliar_portal,
)
from app.vision.schemas import PoseLandmark, PoseResult

QUADRO = (1000, 1000, 3)


def _pessoa(status: dict[str, str], *, caixa=(300, 100, 700, 900), pid="person_1", tid=1):
    x1, y1, x2, y2 = caixa
    return {
        "id": pid,
        "track_id": tid,
        "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "ppe": {k: {"status": v} for k, v in status.items()},
    }


def _estados(r):
    return {i["key"]: i["estado"] for i in r["itens"]}


def test_sem_pessoa_aguarda():
    assert avaliar_portal({"people": []}, ["helmet"], QUADRO)["verdict"] == "waiting"


def test_tudo_confirmado_libera():
    r = avaliar_portal({"people": [_pessoa({"helmet": "ok", "vest": "ok"})]}, ["helmet", "vest"], QUADRO)
    assert r["verdict"] == "approved"
    assert _estados(r) == {"helmet": CONFIRMADO, "vest": CONFIRMADO}


def test_um_faltando_nao_libera():
    r = avaliar_portal({"people": [_pessoa({"helmet": "ok", "vest": "missing"})]}, ["helmet", "vest"], QUADRO)
    assert r["verdict"] == "denied"
    assert _estados(r)["vest"] == FALTANDO


def test_pes_cortados_nao_sao_verificaveis_e_nao_impedem():
    # Caixa encostada na borda de baixo: o calçado não pode ser visto.
    pessoa = _pessoa({"helmet": "ok", "safety_shoe": "missing"}, caixa=(300, 100, 700, 999))
    r = avaliar_portal({"people": [pessoa]}, ["helmet", "safety_shoe"], QUADRO)
    assert _estados(r) == {"helmet": CONFIRMADO, "safety_shoe": NAO_VERIFICAVEL}
    assert r["itens"][1]["motivo"] == "pés fora do quadro"
    assert r["verdict"] == "approved"


def test_maos_sem_keypoint_nao_verificaveis_com_pose():
    pose = PoseResult(
        landmarks=[PoseLandmark("left_wrist", 0.4, 0.5, 0.0, 0.9), PoseLandmark("right_wrist", 0.6, 0.5, 0.0, 0.1)],
        person_id="person_1",
        track_id=1,
    )
    r = avaliar_portal({"people": [_pessoa({"vest": "ok", "gloves": "missing"})]}, ["vest", "gloves"], QUADRO, [pose])
    assert _estados(r)["gloves"] == NAO_VERIFICAVEL


def test_classe_que_o_modelo_nao_tem_e_nao_verificavel():
    r = avaliar_portal({"people": [_pessoa({"helmet": "ok", "ear_protection": "unsupported"})]},
                       ["helmet", "ear_protection"], QUADRO)
    assert _estados(r)["ear_protection"] == NAO_VERIFICAVEL
    assert r["verdict"] == "approved"


def test_nada_verificavel_nao_libera():
    pessoa = _pessoa({"safety_shoe": "missing"}, caixa=(300, 100, 700, 999))
    assert avaliar_portal({"people": [pessoa]}, ["safety_shoe"], QUADRO)["verdict"] == "denied"


def test_usa_a_pessoa_mais_proxima():
    longe = _pessoa({"helmet": "missing"}, caixa=(0, 0, 100, 200), pid="person_2", tid=2)
    perto = _pessoa({"helmet": "ok"})
    r = avaliar_portal({"people": [longe, perto]}, ["helmet"], QUADRO)
    assert r["track_id"] == 1 and r["verdict"] == "approved"


def test_portal_libera_so_depois_de_n_analises_e_conta_um_checkin():
    estado = PortalState(confirmacoes=3)
    ok = avaliar_portal({"people": [_pessoa({"helmet": "ok"})]}, ["helmet"], QUADRO)
    assert estado.atualizar(ok)["verdict"] == "waiting"
    assert estado.atualizar(ok)["verdict"] == "waiting"
    terceiro = estado.atualizar(ok)
    assert terceiro["verdict"] == "approved" and terceiro.get("checkin_novo") is True
    assert "checkin_novo" not in estado.atualizar(ok)
    assert estado.checkins == 1


def test_portal_conta_os_vereditos_brutos_e_o_item_que_faltou():
    estado = PortalState(confirmacoes=3)
    ok = avaliar_portal({"people": [_pessoa({"helmet": "ok"})]}, ["helmet"], QUADRO)
    sem = avaliar_portal({"people": [_pessoa({"helmet": "missing"})]}, ["helmet"], QUADRO)
    for bruto in (ok, sem, ok, ok, sem):
        estado.atualizar(bruto)
    assert estado.brutos == {"approved": 3, "denied": 2, "waiting": 0}
    assert estado.faltas == {"helmet": 2}
    estado.reset()
    assert estado.brutos == {"approved": 0, "denied": 0, "waiting": 0} and estado.faltas == {}



def test_explicacao_diz_o_que_o_modelo_viu_e_o_que_foi_descartado():
    """X9: o portal explica cada item — inclusive o "capacete" que o filtro descartou."""
    from app.services.gate_service import avaliar_portal

    pessoa = {"id": "person_1", "track_id": 1, "box": {"x1": 100, "y1": 50, "x2": 300, "y2": 500},
              "ppe": {"helmet": {"status": "missing", "confidence": 0.0}, "vest": {"status": "ok", "confidence": 0.81}}}
    descartadas = [{"l": "helmet", "c": 0.31, "b": [150, 60, 230, 120], "m": "abaixo do piso 0.40"},
                   {"l": "helmet", "c": 0.9, "b": [600, 60, 700, 120], "m": "fora de qualquer pessoa"}]
    r = avaliar_portal({"people": [pessoa]}, ["helmet", "vest"], (540, 960, 3), (), descartadas, {"helmet": 0.4})
    itens = {i["key"]: i for i in r["itens"]}
    assert itens["vest"]["explicacao"] == "visto com confiança 0,81"
    assert itens["helmet"]["explicacao"].startswith("o modelo viu com 0,31, abaixo do piso")
    assert "descartado" in itens["helmet"]["explicacao"]
    sem = avaliar_portal({"people": [pessoa]}, ["helmet"], (540, 960, 3), (), [], {})
    assert sem["itens"][0]["explicacao"] == "o modelo não viu este item na pessoa"
