"""Escalonamento de alerta crítico sem reconhecimento (MISSÃO 4, M7).

O `Escalonador` não lê relógio nenhum: cada teste passa o `agora`. Os prazos
padrão (60 s e 180 s) são os de `Config`; a regra do editor os sobrescreve
(`metadata.acoes.escalonamento`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app.config import Config
from app.extensions import db
from app.models import Alert, Camera, EventLog, Incidente, PontoDaLiga
from app.services import escalonamento as esc
from app.services.escalonamento import Escalonador, prazos_do_alerta, publicar, registrar_reconhecimento, segundos_ate_reconhecer
from app.services.liga import registrar as liga_registrar

BASE = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)


def _em(segundos: float) -> datetime:
    return BASE + timedelta(seconds=segundos)


def _alerta(alerta_id=1, *, camera_id=1, severity="critical", reconhecido=False, acoes=None, criado=BASE):
    metadata = {"acoes": {"escalonamento": acoes}} if acoes is not None else {}
    return {
        "id": alerta_id,
        "camera_id": camera_id,
        "rule": "fallen_person",
        "severity": severity,
        "message": "Pessoa caída detectada",
        "status": "active",
        "acknowledged": reconhecido,
        "metadata": metadata,
        "created_at": criado.isoformat(),
    }


def _por_camera(*alertas):
    mapa: dict = {}
    for a in alertas:
        mapa.setdefault(a["camera_id"], []).append(a)
    return mapa


# ----------------------------------------------------------------- níveis ---
def test_antes_do_prazo_nao_escalona():
    e = Escalonador(60, 180)
    assert e.avaliar(_por_camera(_alerta()), _em(59.9)) == []
    assert e.camera_escalonada(1) is False


def test_nivel_1_supervisor_aos_60s_e_nivel_2_tv_aos_180s():
    e = Escalonador(60, 180)
    alerta = _alerta()

    [n1] = e.avaliar(_por_camera(alerta), _em(60))
    assert (n1["nivel"], n1["papel"], n1["alerta_id"], n1["camera_id"]) == (1, "supervisor", 1, 1)
    assert n1["regra"] == "fallen_person"
    assert n1["segundos_sem_reconhecer"] == 60.0
    assert (n1["prazo_s"], n1["origem_do_prazo"]) == (60.0, "configuracao")
    assert e.camera_escalonada(1) is False  # nível 1 ainda não pisca a torre

    assert e.avaliar(_por_camera(alerta), _em(179)) == []

    [n2] = e.avaliar(_por_camera(alerta), _em(180))
    assert (n2["nivel"], n2["papel"]) == (2, "tv_torre")
    assert e.camera_escalonada(1) is True


def test_cada_nivel_sai_uma_unica_vez():
    e = Escalonador(60, 180)
    alerta = _alerta()
    todos = []
    for t in (60, 61, 90, 180, 181, 400, 800):
        todos += e.avaliar(_por_camera(alerta), _em(t))
    assert [ev["nivel"] for ev in todos] == [1, 2]
    assert e.camera_escalonada(1) is True  # a marca continua enquanto o alerta continua sem reconhecer


def test_tique_atrasado_emite_os_dois_niveis_em_ordem():
    e = Escalonador(60, 180)
    eventos = e.avaliar(_por_camera(_alerta()), _em(600))
    assert [ev["nivel"] for ev in eventos] == [1, 2]


def test_alerta_que_some_e_volta_nao_escalona_de_novo():
    e = Escalonador(60, 180)
    alerta = _alerta()
    assert len(e.avaliar(_por_camera(alerta), _em(70))) == 1
    assert e.avaliar({}, _em(80)) == []  # worker parado por um tique
    assert e.avaliar(_por_camera(alerta), _em(90)) == []


def test_so_alerta_critico_escalona():
    e = Escalonador(60, 180)
    assert e.avaliar(_por_camera(_alerta(severity="high"), _alerta(2, severity="medium")), _em(1000)) == []
    assert e.camera_escalonada(1) is False


# ------------------------------------------------------ reconhecer encerra ---
def test_reconhecer_antes_do_nivel_1_nao_escalona():
    e = Escalonador(60, 180)
    assert e.avaliar(_por_camera(_alerta(reconhecido=True)), _em(500)) == []
    assert e.camera_escalonada(1) is False


def test_reconhecer_entre_os_niveis_encerra_e_apaga_a_marca():
    e = Escalonador(60, 180)
    alerta = _alerta()
    assert [ev["nivel"] for ev in e.avaliar(_por_camera(alerta), _em(100))] == [1]
    assert e.avaliar(_por_camera(_alerta(reconhecido=True)), _em(200)) == []  # nível 2 não sai
    assert e.camera_escalonada(1) is False


def test_reconhecer_depois_do_nivel_2_apaga_a_marca_da_camera():
    e = Escalonador(60, 180)
    e.avaliar(_por_camera(_alerta()), _em(200))
    assert e.camera_escalonada(1) is True
    e.avaliar(_por_camera(_alerta(reconhecido=True)), _em(210))
    assert e.camera_escalonada(1) is False


def test_alerta_resolvido_sai_do_resumo_e_apaga_a_marca():
    e = Escalonador(60, 180)
    e.avaliar(_por_camera(_alerta()), _em(200))
    e.avaliar({1: []}, _em(201))
    assert e.camera_escalonada(1) is False


def test_marca_e_por_camera():
    e = Escalonador(60, 180)
    e.avaliar(_por_camera(_alerta(1, camera_id=1), _alerta(2, camera_id=2, criado=_em(150))), _em(200))
    assert e.camera_escalonada(1) is True
    assert e.camera_escalonada(2) is False  # a câmera 2 espera há 50 s: nenhum nível ainda
    resumos = [{"id": 1}, {"id": 2}, {"id": 3}]
    e.marcar(resumos)
    assert [r["escalonado"] for r in resumos] == [True, False, False]


# ------------------------------------------------------ prazos regra x config ---
def test_prazos_da_regra_valem_no_lugar_da_configuracao():
    e = Escalonador(60, 180)
    alerta = _alerta(acoes={"supervisor_s": 10, "tv_s": 20})
    [n1] = e.avaliar(_por_camera(alerta), _em(10))
    assert (n1["nivel"], n1["prazo_s"], n1["origem_do_prazo"]) == (1, 10.0, "regra")
    [n2] = e.avaliar(_por_camera(alerta), _em(20))
    assert (n2["nivel"], n2["prazo_s"]) == (2, 20.0)


def test_regra_com_so_um_prazo_herda_o_outro_da_configuracao():
    prazos = prazos_do_alerta(_alerta(acoes={"supervisor_s": 30, "tv_s": None}), 60, 180)
    assert (prazos.supervisor_s, prazos.tv_s, prazos.origem) == (30.0, 180.0, "regra")
    prazos = prazos_do_alerta(_alerta(acoes={"supervisor_s": None, "tv_s": 90}), 60, 180)
    assert (prazos.supervisor_s, prazos.tv_s, prazos.origem) == (60.0, 90.0, "regra")


def test_regra_sem_escalonamento_usa_a_configuracao():
    for alerta in (_alerta(), _alerta(acoes={"supervisor_s": None, "tv_s": None}), _alerta(acoes={})):
        prazos = prazos_do_alerta(alerta, 60, 180)
        assert (prazos.supervisor_s, prazos.tv_s, prazos.origem) == (60.0, 180.0, "configuracao")


@pytest.mark.parametrize("invalido", [0, -5, True, "30", None])
def test_prazo_invalido_na_regra_cai_para_a_configuracao(invalido):
    prazos = prazos_do_alerta(_alerta(acoes={"supervisor_s": invalido, "tv_s": invalido}), 60, 180)
    assert (prazos.supervisor_s, prazos.tv_s, prazos.origem) == (60.0, 180.0, "configuracao")


def test_nivel_2_nunca_vem_antes_do_nivel_1():
    # a regra pede supervisor em 300 s; o tv_s herdado (180) subiria para 300 também
    prazos = prazos_do_alerta(_alerta(acoes={"supervisor_s": 300, "tv_s": None}), 60, 180)
    assert (prazos.supervisor_s, prazos.tv_s) == (300.0, 300.0)
    e = Escalonador(60, 180)
    eventos = e.avaliar(_por_camera(_alerta(acoes={"supervisor_s": 300, "tv_s": None})), _em(250))
    assert eventos == []


def test_escalonador_da_configuracao_le_as_chaves_e_o_padrao_e_60_e_180():
    assert (Config.ESCALONAR_SUPERVISOR_S, Config.ESCALONAR_TV_S) == (60.0, 180.0)
    e = Escalonador.da_configuracao({"ESCALONAR_SUPERVISOR_S": 5, "ESCALONAR_TV_S": 9})
    assert [ev["nivel"] for ev in e.avaliar(_por_camera(_alerta()), _em(9))] == [1, 2]
    padrao = Escalonador.da_configuracao({})
    assert (padrao.supervisor_s, padrao.tv_s) == (60.0, 180.0)


# ------------------------------------------------------- estado da planta ---
def test_campo_escalonado_chega_ao_estado_da_planta():
    from app.services.integracao.estado import estado_da_planta

    e = Escalonador(60, 180)
    e.avaliar(_por_camera(_alerta()), _em(200))
    resumo = {"id": 1, "nome": "Pátio", "estado": "alarme", "incidentes_criticos": 1, "incidentes_por_regra": {"fallen_person": 1}}
    e.marcar([resumo])
    cameras = estado_da_planta([resumo])["cameras"]
    assert cameras[0]["escalonado"] is True
    assert estado_da_planta([{"id": 1, "nome": "x"}])["cameras"][0]["escalonado"] is False


# ---------------------------------------------------------------- publicar ---
class _Socket:
    def __init__(self):
        self.emitidos = []

    def emit(self, evento, payload=None, *args, **kwargs):
        self.emitidos.append((evento, payload, kwargs))


def test_publicar_emite_para_a_sala_do_parque_e_grava_na_linha_do_tempo(app):
    eventos = Escalonador(60, 180).avaliar(_por_camera(_alerta()), _em(200))
    socket = _Socket()
    publicar(eventos, socket, app)

    assert [(nome, kw["to"]) for nome, _payload, kw in socket.emitidos] == [("escalonamento", "parque")] * 2
    assert [p["nivel"] for _n, p, _kw in socket.emitidos] == [1, 2]
    linhas = EventLog.query.filter_by(event_type="alerta_escalonado").order_by(EventLog.id).all()
    assert [linha.metadata_json["nivel"] for linha in linhas] == [1, 2]
    assert linhas[0].camera_id == 1 and linhas[0].subject == "alerta:1"
    assert "supervisor" in linhas[0].message and "TV" in linhas[1].message


def test_falha_ao_emitir_nao_derruba_o_tique(app):
    class Quebrado:
        def emit(self, *a, **k):
            raise RuntimeError("sem rede")

    eventos = Escalonador(60, 180).avaliar(_por_camera(_alerta()), _em(70))
    publicar(eventos, Quebrado(), app)  # não levanta
    assert EventLog.query.filter_by(event_type="alerta_escalonado").count() == 1


# ------------------------------------------------ tempo até reconhecer (Liga) ---
def test_segundos_ate_reconhecer():
    assert segundos_ate_reconhecer(BASE, _em(42.5).isoformat()) == 42.5
    assert segundos_ate_reconhecer(BASE.replace(tzinfo=None), _em(10)) == 10.0  # sem fuso = UTC, como o banco
    assert segundos_ate_reconhecer(BASE, None) is None
    assert segundos_ate_reconhecer("lixo", _em(1)) is None
    assert segundos_ate_reconhecer(_em(10), BASE) == 0.0  # nunca negativo


def _alerta_do_banco(*, ack_em_s, incidente_id=None, camera_id=None):
    metadata = {"acknowledged": True, "acknowledged_at": _em(ack_em_s).isoformat()}
    if incidente_id is not None:
        metadata["incidente_id"] = incidente_id
    alerta = Alert(camera_id=camera_id, rule="fallen_person", severity="critical", message="Pessoa caída",
                   status="active", metadata_json=metadata, created_at=BASE)
    db.session.add(alerta)
    db.session.commit()
    return alerta


@pytest.fixture()
def camera(app):
    camera = Camera(name="Pátio", location="Setor A", source="0")
    db.session.add(camera)
    db.session.commit()
    return camera


@pytest.mark.parametrize(
    ("segundos", "tipo"), [(30, "reconhecido_rapido"), (60, "reconhecido_rapido"), (61, "reconhecido"), (180, "reconhecido")]
)
def test_reconhecer_rapido_vira_ponto_positivo_do_setor(app, camera, segundos, tipo):
    resultado = registrar_reconhecimento(_alerta_do_banco(ack_em_s=segundos, camera_id=camera.id))
    assert resultado == {"segundos": float(segundos), "ponto": tipo}
    [ponto] = PontoDaLiga.query.all()
    assert (ponto.tipo, ponto.setor, ponto.pontos > 0) == (tipo, "Setor A", True)


def test_reconhecer_devagar_mede_mas_nao_pontua_e_nao_penaliza(app, camera):
    resultado = registrar_reconhecimento(_alerta_do_banco(ack_em_s=900, camera_id=camera.id))
    assert resultado == {"segundos": 900.0, "ponto": None}
    assert PontoDaLiga.query.count() == 0  # sem ponto, e nenhum ponto negativo


def test_alerta_sem_hora_de_reconhecimento_nao_e_medido(app, camera):
    alerta = Alert(camera_id=camera.id, rule="r", severity="critical", message="m", status="active", metadata_json={}, created_at=BASE)
    db.session.add(alerta)
    db.session.commit()
    assert registrar_reconhecimento(alerta) is None


def test_reconhecer_alerta_e_o_incidente_dele_vale_um_ponto_so(app, camera):
    incidente = Incidente(camera_id=camera.id, rule="fallen_person", severity="critical", titulo="Queda", aberto_em=BASE)
    db.session.add(incidente)
    db.session.commit()

    # o alerta é reconhecido a 30 s da abertura do incidente...
    resultado = registrar_reconhecimento(_alerta_do_banco(ack_em_s=30, incidente_id=incidente.id, camera_id=camera.id))
    assert resultado["ponto"] == "reconhecido_rapido"
    # ...e o incidente, depois, a 120 s (faixa "reconhecido"): o mesmo fato não soma de novo
    assert liga_registrar("reconhecido", ref=f"incidente:{incidente.id}", camera_id=camera.id) is None
    assert liga_registrar("reconhecido_rapido", ref=f"incidente:{incidente.id}", camera_id=camera.id) is None
    assert PontoDaLiga.query.count() == 1


def test_o_relogio_do_alerta_de_um_incidente_e_o_da_abertura_do_incidente(app, camera):
    # incidente aberto há 5 min; o alerta novo dele é reconhecido 10 s depois de criado: NÃO é "rápido"
    incidente = Incidente(camera_id=camera.id, rule="fallen_person", severity="critical", titulo="Queda", aberto_em=BASE)
    db.session.add(incidente)
    db.session.commit()
    alerta = _alerta_do_banco(ack_em_s=310, incidente_id=incidente.id, camera_id=camera.id)
    alerta.created_at = _em(300)
    db.session.commit()
    assert registrar_reconhecimento(alerta) == {"segundos": 310.0, "ponto": None}


def test_a_mesma_faixa_continua_sem_duplicar(app, camera):
    assert liga_registrar("checkin_portal", ref="x", camera_id=camera.id) is not None
    assert liga_registrar("checkin_portal", ref="x", camera_id=camera.id) is None
    assert esc.PAPEL_DO_NIVEL == {1: "supervisor", 2: "tv_torre"}
