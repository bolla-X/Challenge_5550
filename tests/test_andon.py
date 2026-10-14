"""G8: minutos conformes por câmera/setor e conquistas — só indicadores positivos."""

from __future__ import annotations

from app.services.andon import (
    MINUTOS_MINIMOS_PARA_CONQUISTA,
    ContadorDeMinutos,
    agregar_setor,
    conformidade_do_quadro,
    conquistas,
)

EXIGIDOS = ["helmet", "vest"]


def _p(**status):
    return {"ppe": {k: {"status": v} for k, v in status.items()}}


CONFORME = [_p(helmet="ok", vest="ok")]
SEM_CAPACETE = [_p(helmet="missing", vest="ok")]


def test_conformidade_ignora_o_que_nao_e_verificavel():
    ok, total, por_epi = conformidade_do_quadro([_p(helmet="ok", vest="unsupported")], EXIGIDOS)
    assert (ok, total) == (1, 1) and por_epi == {"helmet": True}


def _minutos(contador, quadros_por_minuto):
    """Cada item: lista de `people` por análise naquele minuto."""
    for m, analises in enumerate(quadros_por_minuto):
        for i, people in enumerate(analises):
            contador.registrar(people, EXIGIDOS, m * 60 + i)
    contador.registrar([], EXIGIDOS, len(quadros_por_minuto) * 60 + 1)  # fecha o último


def test_minuto_sem_pessoa_e_neutro_nao_conta_nem_quebra():
    c = ContadorDeMinutos()
    _minutos(c, [[CONFORME], [[]], [CONFORME]])
    r = c.resumo()
    assert r["minutos_com_pessoas"] == 2
    assert r["minutos_conformes"] == 2
    assert r["sequencia_min"] == 2


def test_uma_falha_no_minuto_quebra_a_sequencia():
    c = ContadorDeMinutos()
    _minutos(c, [[CONFORME], [CONFORME, SEM_CAPACETE], [CONFORME]])
    r = c.resumo()
    assert r["minutos_conformes"] == 2 and r["sequencia_min"] == 1 and r["melhor_sequencia_min"] == 1
    assert r["epis_sempre_ok"] == ["vest"]


def test_camera_vazia_o_turno_inteiro_nao_ganha_nada():
    c = ContadorDeMinutos()
    _minutos(c, [[[]]] * 30)
    setor = agregar_setor("Doca", [{**c.resumo(), "checkins_portal": 0}])
    assert setor["minutos_conformes"] == 0
    assert conquistas(setor, {"minutos_conformes": 0}) == []


def test_conquista_de_100_porcento_exige_minutos_minimos():
    c = ContadorDeMinutos()
    _minutos(c, [[CONFORME]] * (MINUTOS_MINIMOS_PARA_CONQUISTA - 1))
    setor = agregar_setor("Doca", [{**c.resumo(), "checkins_portal": 0}])
    assert conquistas(setor, {}) == []
    c2 = ContadorDeMinutos()
    _minutos(c2, [[CONFORME]] * MINUTOS_MINIMOS_PARA_CONQUISTA)
    setor = agregar_setor("Doca", [{**c2.resumo(), "checkins_portal": 0}])
    assert {x["id"] for x in conquistas(setor, {})} == {"turno_100_helmet", "turno_100_vest"}


def test_metas_do_setor():
    setor = {"minutos_com_pessoas": 0, "minutos_conformes": 30, "epis_sempre_ok": [], "checkins_portal": 5}
    ids = {x["id"] for x in conquistas(setor, {"minutos_conformes": 30, "checkins_portal": 6})}
    assert ids == {"meta_minutos"}


def test_setor_soma_cameras_e_sequencia_e_a_menor():
    a, b = ContadorDeMinutos(), ContadorDeMinutos()
    _minutos(a, [[CONFORME]] * 5)
    _minutos(b, [[CONFORME]] * 2)
    setor = agregar_setor("Doca", [{**a.resumo(), "checkins_portal": 1}, {**b.resumo(), "checkins_portal": 2}])
    assert setor["minutos_conformes"] == 7
    assert setor["sequencia_min"] == 2
    assert setor["checkins_portal"] == 3


def test_nada_por_pessoa_no_resumo():
    c = ContadorDeMinutos()
    _minutos(c, [[CONFORME]])
    texto = repr(c.resumo())
    assert "person" not in texto and "track" not in texto
