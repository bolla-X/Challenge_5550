"""Estado vivo da planta (M2): resumo dos workers → torre, OPC UA e MQTT.

Os clientes OPC UA e MQTT aqui são REAIS (asyncua e paho contra o servidor e o
broker embutidos, em portas livres): o alerta crítico de uma câmera tem de
aparecer no nó `PlantaEmAlarme` e no tópico `visionepi/<camera>/alerta`.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from app.services.integracao.gerente import GerenteDeIntegracao
from app.services.integracao.planta_viva import PublicadorDaPlanta, resumo_da_camera

pytestmark = pytest.mark.timeout(90)


class _Evento:
    def __init__(self, ligado=True):
        self._v = ligado

    def is_set(self):
        return self._v


class _Status:
    def __init__(self, estado):
        self._e = estado

    def to_dict(self):
        return {"state": self._e}


class _Video:
    def __init__(self, estado="live"):
        self.estado = estado

    def status(self):
        return _Status(self.estado)


class _Alertas:
    def __init__(self):
        self.ativos: list[dict] = []

    def active_alerts(self):
        return list(self.ativos)

    def active_incidents(self):
        return [{"id": i, "rule": a["rule"]} for i, a in enumerate(self.ativos)]


class _Andon:
    def resumo(self):
        return {"conformidade_atual": 0.5}


class _Saude:
    def __init__(self, estado="ok"):
        self.e = estado

    def estado(self):
        return {"estado": self.e}


class WorkerFalso:
    def __init__(self, camera_id, rodando=True):
        self.camera_id = camera_id
        self._running = _Evento(rodando)
        self.alert_state_service = _Alertas()
        self.video_stream = _Video()
        self.andon = _Andon()
        self.saude_visual = _Saude()


def _alerta(i, sev="critical", ack=False, regra="missing_helmet"):
    return {"id": i, "rule": regra, "severity": sev, "message": f"Sem capacete · Pessoa {i}", "acknowledged": ack,
            "created_at": f"2026-10-17T10:00:0{i}+00:00"}


def test_camera_sem_alerta_e_ok_e_torre_verde():
    w = WorkerFalso(1)
    pub = PublicadorDaPlanta(lambda: [(w, "Canteiro")], gerente=None)
    estado = pub.tique()
    assert estado["torre"] == "verde" and not estado["planta_em_alarme"] and not estado["sirene"]
    assert estado["cameras"][0]["nome"] == "Canteiro"


def test_alerta_critico_nao_reconhecido_acende_vermelho_com_sirene_e_reconhecer_cala():
    w = WorkerFalso(1)
    w.alert_state_service.ativos = [_alerta(1)]
    pub = PublicadorDaPlanta(lambda: [(w, "Multidão")], gerente=None)
    estado = pub.tique()
    assert estado["torre"] == "vermelho" and estado["sirene"] is True and estado["planta_em_alarme"] is True
    w.alert_state_service.ativos = [_alerta(1, ack=True)]
    estado = pub.tique()
    assert estado["torre"] == "vermelho" and estado["sirene"] is False


def test_alerta_nao_critico_e_amarelo_e_camera_parada_e_offline():
    w = WorkerFalso(1)
    w.alert_state_service.ativos = [_alerta(1, sev="high", regra="missing_vest")]
    parada = WorkerFalso(2, rodando=False)
    resumo = resumo_da_camera(parada, "Rede")
    assert resumo["estado"] == "offline"
    estado = PublicadorDaPlanta(lambda: [(w, "A"), (parada, "B")], gerente=None).tique()
    assert estado["torre"] == "amarelo"


@pytest.mark.parametrize(("saude", "torre"), [("obstruida", "vermelho"), ("movida", "vermelho"), ("escura", "amarelo"),
                                              ("ofuscada", "amarelo"), ("desfocada", "amarelo")])
def test_saude_visual_entra_na_torre(saude, torre):
    w = WorkerFalso(1)
    w.saude_visual = _Saude(saude)
    assert PublicadorDaPlanta(lambda: [(w, "A")], gerente=None).tique()["torre"] == torre


def test_publica_so_alerta_novo():
    publicados = []

    class GerenteFalso:
        def publicar_alerta(self, cid, a):
            publicados.append((cid, a["id"]))

        def publicar_estado(self, e):
            pass

    w = WorkerFalso(3)
    pub = PublicadorDaPlanta(lambda: [(w, "A")], gerente=GerenteFalso())
    w.alert_state_service.ativos = [_alerta(1)]
    pub.tique()  # primeiro tique só aprende o que já estava ativo
    w.alert_state_service.ativos = [_alerta(1), _alerta(2)]
    pub.tique()
    pub.tique()
    assert publicados == [(3, 2)]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_alerta_chega_no_opcua_e_no_mqtt_com_clientes_reais():
    import paho.mqtt.client as mqtt
    from asyncua.sync import Client

    porta_opc, porta_mqtt = _porta_livre(), _porta_livre()
    gerente = GerenteDeIntegracao({"OPCUA_ATIVO": True, "OPCUA_HOST": "127.0.0.1", "OPCUA_PORTA": porta_opc,
                                   "MQTT_ATIVO": True, "MQTT_HOST": "127.0.0.1", "MQTT_PORTA": porta_mqtt,
                                   "MQTT_BROKER_EMBUTIDO": True})
    recebidos: list[tuple[str, dict]] = []
    chegou = threading.Event()
    assinante = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def ao_receber(_c, _u, msg):
        recebidos.append((msg.topic, json.loads(msg.payload)))
        if msg.topic.endswith("/alerta"):
            chegou.set()

    assinante.on_message = ao_receber
    try:
        status = gerente.iniciar()
        assert status["opcua"]["estado"] == "no_ar", status
        assert status["broker"]["estado"] == "no_ar", status
        assinante.connect("127.0.0.1", porta_mqtt)
        assinante.subscribe("visionepi/#", qos=1)
        assinante.loop_start()
        time.sleep(0.5)

        w = WorkerFalso(7)
        pub = PublicadorDaPlanta(lambda: [(w, "Multidão")], gerente=gerente)
        pub.tique()
        w.alert_state_service.ativos = [_alerta(5)]
        pub.tique()

        assert chegou.wait(10), recebidos
        topico, corpo = next(r for r in recebidos if r[0].endswith("/alerta"))
        assert topico == "visionepi/7/alerta" and corpo["severidade"] == "critical" and corpo["id"] == 5

        cliente = Client(f"opc.tcp://127.0.0.1:{porta_opc}/visionepi/")
        cliente.connect()
        try:
            idx = cliente.get_namespace_index("urn:visionepi")
            fim = time.monotonic() + 10
            while time.monotonic() < fim:
                alarme = cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value()
                if alarme:
                    break
                time.sleep(0.2)
            assert alarme is True
            assert cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() == "vermelho"
            assert cliente.get_node(f"ns={idx};s=Cameras.Camera_7.Estado").read_value() == "alarme"
            assert cliente.get_node(f"ns={idx};s=Cameras.Camera_7.IncidentesAtivos.missing_helmet").read_value() == 1

            # Reconhecido e resolvido: torre volta a verde no OPC UA.
            w.alert_state_service.ativos = []
            pub.tique()
            fim = time.monotonic() + 10
            while time.monotonic() < fim and cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() != "verde":
                time.sleep(0.2)
            assert cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() == "verde"
            assert cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value() is False
        finally:
            cliente.disconnect()
    finally:
        assinante.loop_stop()
        assinante.disconnect()
        gerente.parar()


def test_api_estado_por_papel(real_monitor_app_auth=None):
    """A rota existe na matriz de permissões (tests/test_matriz_de_permissoes.py); aqui só o formato."""
    from app import create_app
    from app.config import TestConfig

    class Cfg(TestConfig):
        AUTH_REQUIRED = False

    app = create_app(Cfg)
    with app.test_client() as c:
        r = c.get("/api/integracao/estado")
        assert r.status_code == 200
        corpo = r.get_json()
        assert set(corpo) == {"planta", "integracoes"}
        assert corpo["planta"]["torre"] in ("verde", "amarelo", "vermelho")
        assert set(corpo["integracoes"]) == {"opcua", "mqtt", "broker", "webhook"}
        assert corpo["integracoes"]["opcua"]["estado"] == "desligado"
