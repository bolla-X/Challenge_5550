"""Controlador adaptativo: limites, histerese e recuperação."""

from __future__ import annotations

from app.services.controlador_adaptativo import ControladorAdaptativo


def controlador(**kw):
    base = dict(n_base=3, n_max=5, telemetria_base_hz=8.0,
                limite_alto_ms=1500, limite_baixo_ms=600, ticks_para_degradar=3, ticks_para_recuperar=5)
    return ControladorAdaptativo(**(base | kw))


def test_escada_tem_a_ordem_prometida():
    c = controlador()
    degraus = c.degraus()
    assert [d["n"] for d in degraus[:3]] == [3, 4, 5], "primeiro reduz a frequência de detecção"
    assert degraus[-1]["telemetria_hz"] == 4.0, "por último, a telemetria do painel"
    assert len(degraus) == 4, "nenhum degrau além de frequência e telemetria"


def test_nenhum_degrau_mexe_na_resolucao_do_modelo():
    """640 é a referência do guarda; toda resolução menor foi reprovada nele."""
    c = controlador(pose_k_max=3)
    assert all(set(d) == {"n", "pose_k", "telemetria_hz"} for d in c.degraus())
    for _ in range(100):
        c.avaliar(99999)
    assert not any("resolução" in r for r in c.reducoes())


def test_monitor_no_nivel_maximo_mantem_imgsz_640(real_monitor_app):
    monitor = real_monitor_app.extensions["monitor_service"]
    for _ in range(100):
        monitor.controlador.avaliar(99999)
    monitor._aplicar_adaptativo([])
    assert monitor.controlador.estado.nivel == monitor.controlador.nivel_max
    assert monitor.detector.imgsz == 640
    assert monitor.person_detector.imgsz == 640


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
    assert any("detecção a cada 5 quadros" in r for r in resumo["reducoes"])
    assert any("painel atualiza 4x/s" in r for r in resumo["reducoes"])
    assert "análise atrasada" in resumo["motivo"]


def test_com_pose_yolo_reduz_a_frequencia_da_pose_antes_da_telemetria():
    c = controlador(pose_k_max=3)
    degraus = c.degraus()
    ks = [d["pose_k"] for d in degraus]
    assert ks.index(2) < [d["telemetria_hz"] for d in degraus].index(4.0), "pose antes da telemetria"
    for _ in range(3 * 4):
        c.avaliar(5000)
    assert any("pose a cada" in r for r in c.reducoes())


def test_no_modo_assincrono_a_escada_comeca_pela_pose(real_monitor_app):
    """Detectar a cada N quadros não reduz carga quando a inferência é o gargalo."""
    monitor = real_monitor_app.extensions["monitor_service"]
    assert monitor.agendador is not None
    degraus = monitor.controlador.degraus()
    assert {d["n"] for d in degraus} == {monitor.controlador.n_base}
    if monitor.pose_detector is not None:
        assert degraus[1]["pose_k"] == 2, "o primeiro degrau já é a pose"
