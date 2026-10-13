"""Controlador adaptativo: limites, histerese e recuperação."""

from __future__ import annotations

from app.services.controlador_adaptativo import ControladorAdaptativo


def controlador(**kw):
    base = dict(n_base=3, n_max=5, imgsz_base=416, imgsz_permitidos=[416, 320], telemetria_base_hz=8.0,
                limite_alto_ms=1500, limite_baixo_ms=600, ticks_para_degradar=3, ticks_para_recuperar=5)
    return ControladorAdaptativo(**(base | kw))


def test_escada_tem_a_ordem_prometida_e_respeita_o_guarda():
    c = controlador()
    degraus = c.degraus()
    assert [d["n"] for d in degraus[:3]] == [3, 4, 5], "primeiro reduz a frequência de detecção"
    assert degraus[3]["imgsz"] == 320, "depois a resolução, só para valor aprovado"
    assert all(d["imgsz"] in (416, 320) for d in degraus), "nunca abaixo do que passou no guarda"
    assert degraus[-1]["telemetria_hz"] == 4.0, "por último, a telemetria do painel"


def test_sem_imgsz_aprovado_abaixo_do_base_nao_mexe_na_resolucao():
    c = controlador(imgsz_permitidos=[416])
    assert {d["imgsz"] for d in c.degraus()} == {416}


def test_degrada_so_depois_de_leituras_seguidas_acima_do_limite():
    c = controlador()
    assert c.avaliar(2000) is False
    assert c.avaliar(2000) is False
    assert c.avaliar(2000) is True
    assert c.estado.nivel == 1
    assert c.reducoes() == ["detecção a cada 4 quadros (era 3)"]


def test_um_pico_isolado_nao_degrada():
    c = controlador()
    for valor in (2000, 2000, 900, 2000, 2000, 900):
        assert c.avaliar(valor) is False
    assert c.estado.nivel == 0, "a banda morta zera a contagem"


def test_recupera_um_degrau_por_vez_e_so_com_folga_sustentada():
    c = controlador()
    for _ in range(9):
        c.avaliar(5000)
    assert c.estado.nivel == 3
    for _ in range(4):
        assert c.avaliar(100) is False
    assert c.avaliar(100) is True
    assert c.estado.nivel == 2, "recupera UM degrau"


def test_nao_passa_dos_limites_da_escada():
    c = controlador()
    for _ in range(100):
        c.avaliar(99999)
    assert c.estado.nivel == c.nivel_max
    for _ in range(100):
        c.avaliar(0)
    assert c.estado.nivel == 0
    assert c.reducoes() == []


def test_sem_metrica_nao_decide():
    c = controlador()
    c.avaliar(2000)
    c.avaliar(2000)
    assert c.avaliar(None) is False
    assert c.avaliar(2000) is False, "a contagem recomeçou depois do buraco"


def test_resumo_diz_ao_operador_o_que_foi_reduzido():
    c = controlador()
    for _ in range(12):
        c.avaliar(5000)
    resumo = c.resumo()
    assert resumo["degradado"] is True
    assert any("resolução do modelo 320" in r for r in resumo["reducoes"])
    assert "análise atrasada" in resumo["motivo"]
