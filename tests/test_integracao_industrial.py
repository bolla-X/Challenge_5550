"""Integração industrial (M2): OPC UA, MQTT (com broker embutido), webhook e degradação.

São testes de INTEGRAÇÃO de verdade: sobem os servidores no loopback em portas
livres e conversam com clientes reais (asyncua.sync.Client, paho-mqtt, um
http.server local). Nada de mock do que está sendo testado; as únicas injeções
são o relógio do gerente e o resolvedor de DNS do webhook (as duas costuras
existem para isso).
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as paho
import pytest
from app.services.integracao.broker import BrokerEmbutido
from app.services.integracao.estado import estado_da_planta
from app.services.integracao.gerente import GerenteDeIntegracao
from app.services.integracao.mqtt import PublicadorMQTT
from app.services.integracao.opcua import ServidorOPCUA
from app.services.integracao.webhook import UrlWebhookInvalida, Webhook
from asyncua import ua
from asyncua.sync import Client

pytestmark = pytest.mark.timeout(60)

_THREADS_DA_INTEGRACAO = ("opcua-servidor", "mqtt-broker-embutido", "webhook-envio")


# -- utilidades ----------------------------------------------------------------


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar(condicao, prazo_s: float = 8.0, intervalo_s: float = 0.05):
    """Repete `condicao()` até devolver algo verdadeiro (e o devolve) ou estourar o prazo."""
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        valor = condicao()
        if valor:
            return valor
        time.sleep(intervalo_s)
    return condicao()


def _camera(id_=1, estado="ok", incidentes=None, **extra):
    return {
        "id": id_,
        "nome": f"Câmera {id_}",
        "estado": estado,
        "incidentes_por_regra": incidentes or {},
        "conformidade": 0.9,
        "ultimo_alerta": None,
        "saude_visual": "ok",
        "critico_nao_reconhecido": False,
        **extra,
    }


def _estado_vermelho():
    return estado_da_planta(
        [
            _camera(
                1,
                "alarme",
                {"sem_capacete": 2, "sem_colete": 1},
                conformidade=0.5,
                ultimo_alerta={"mensagem": "Sem capacete na Linha 1", "severidade": "critico", "ts": "2026-10-17T10:00:00+00:00"},
                critico_nao_reconhecido=True,
            )
        ]
    )


def _estado_verde():
    return estado_da_planta([_camera(1, "ok", {"sem_capacete": 0}, conformidade=1.0)])


@pytest.fixture(autouse=True)
def sem_threads_vazados():
    yield
    vivos = _esperar(
        lambda: not [t for t in threading.enumerate() if t.name in _THREADS_DA_INTEGRACAO and t.is_alive()], prazo_s=5
    )
    restantes = [t.name for t in threading.enumerate() if t.name in _THREADS_DA_INTEGRACAO and t.is_alive()]
    assert vivos, f"threads da integração ficaram vivos após o teste: {restantes}"


@pytest.fixture
def servidor_opcua():
    servidor = ServidorOPCUA(porta=_porta_livre())
    status = servidor.iniciar()
    try:
        assert status["estado"] == "no_ar", status
        yield servidor
    finally:
        servidor.parar()


@pytest.fixture
def broker():
    broker = BrokerEmbutido(porta=_porta_livre())
    status = broker.iniciar()
    try:
        assert status["estado"] == "no_ar", status
        yield broker
    finally:
        broker.parar()


class _Assinante:
    """Cliente paho que assina um filtro e guarda o que chega (topico, json, retain)."""

    def __init__(self, porta: int, filtro: str = "visionepi/#") -> None:
        self.mensagens: queue.Queue[tuple[str, object, bool]] = queue.Queue()
        self._assinado = threading.Event()
        self._cliente = paho.Client(paho.CallbackAPIVersion.VERSION2)
        self._cliente.on_connect = lambda c, d, f, rc, p=None: c.subscribe(filtro, qos=1)
        self._cliente.on_subscribe = lambda c, d, mid, rcs, p=None: self._assinado.set()
        self._cliente.on_message = lambda c, d, m: self.mensagens.put((m.topic, json.loads(m.payload), bool(m.retain)))
        self._cliente.connect("127.0.0.1", porta)
        self._cliente.loop_start()
        assert self._assinado.wait(5), "o assinante não conseguiu assinar no broker"

    def receber(self, quantas: int, prazo_s: float = 8.0) -> list[tuple[str, object, bool]]:
        recebidas = []
        limite = time.monotonic() + prazo_s
        while len(recebidas) < quantas and time.monotonic() < limite:
            try:
                recebidas.append(self.mensagens.get(timeout=0.2))
            except queue.Empty:
                continue
        return recebidas

    def fechar(self) -> None:
        self._cliente.disconnect()
        self._cliente.loop_stop()


@pytest.fixture
def assinantes():
    abertos: list[_Assinante] = []

    def criar(porta: int, filtro: str = "visionepi/#") -> _Assinante:
        assinante = _Assinante(porta, filtro)
        abertos.append(assinante)
        return assinante

    yield criar
    for assinante in abertos:
        assinante.fechar()


class _ReceptorHTTP:
    """Servidor HTTP local de teste: guarda cada POST e responde o status configurado por caminho."""

    def __init__(self) -> None:
        self.recebidos: list[dict] = []
        dono = self

        class Tratador(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho)
                dono.recebidos.append(
                    {"caminho": self.path, "tipo": self.headers.get("Content-Type"), "json": json.loads(corpo or b"null")}
                )
                if self.path.startswith("/redireciona"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{dono.porta}/destino")
                else:
                    self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        self.porta = self._servidor.server_address[1]
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()

    def url(self, caminho: str = "/hook") -> str:
        return f"http://127.0.0.1:{self.porta}{caminho}"

    def fechar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def receptor_http():
    receptor = _ReceptorHTTP()
    yield receptor
    receptor.fechar()


# -- estado_da_planta ------------------------------------------------------------


def test_estado_verde_quando_tudo_ok():
    estado = estado_da_planta([_camera(1), _camera(2)], agora=datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc))
    assert estado["torre"] == "verde"
    assert estado["planta_em_alarme"] is False
    assert estado["sirene"] is False
    assert estado["ts"] == "2026-10-17T12:00:00+00:00"
    assert [c["id"] for c in estado["cameras"]] == [1, 2]


def test_estado_sem_cameras_e_verde():
    assert estado_da_planta([])["torre"] == "verde"


@pytest.mark.parametrize(
    "camera",
    [
        _camera(1, "atencao", {"sem_oculos": 1}, incidentes_criticos=0),
        _camera(1, "ok", {"sem_luva": 3}),
        _camera(1, "offline"),
        _camera(1, "ok", saude_visual="degradada"),
        _camera(1, "ok", saude_visual="Desfocada"),
    ],
)
def test_estado_amarelo_para_incidente_nao_critico_offline_ou_visao_degradada(camera):
    estado = estado_da_planta([_camera(2), camera])
    assert estado["torre"] == "amarelo"
    assert estado["planta_em_alarme"] is False
    assert estado["sirene"] is False


@pytest.mark.parametrize(
    "camera",
    [
        _camera(1, "alarme", {"sem_capacete": 1}),
        _camera(1, "alarme"),
        _camera(1, "atencao", {"sem_capacete": 1}, incidentes_criticos=1),
        _camera(1, "ok", saude_visual="obstruída"),
        _camera(1, "ok", saude_visual="movida"),
    ],
)
def test_estado_vermelho_para_incidente_critico_ou_camera_cega(camera):
    estado = estado_da_planta([camera])
    assert estado["torre"] == "vermelho"
    assert estado["planta_em_alarme"] is True


def test_vermelho_vence_amarelo():
    estado = estado_da_planta([_camera(1, "offline"), _camera(2, "alarme", {"sem_capacete": 1})])
    assert estado["torre"] == "vermelho"


def test_sirene_exige_vermelho_com_critico_nao_reconhecido():
    nao_reconhecido = estado_da_planta([_camera(1, "alarme", {"x": 1}, critico_nao_reconhecido=True)])
    assert nao_reconhecido["sirene"] is True
    # Reconhecido: a sirene cala, a torre continua vermelha enquanto o incidente durar.
    reconhecido = estado_da_planta([_camera(1, "alarme", {"x": 1}, critico_nao_reconhecido=False)])
    assert reconhecido["torre"] == "vermelho" and reconhecido["sirene"] is False
    # Torre amarela nunca toca sirene, mesmo com a flag.
    amarelo = estado_da_planta([_camera(1, "offline", critico_nao_reconhecido=True)])
    assert amarelo["torre"] == "amarelo" and amarelo["sirene"] is False


def test_estado_normaliza_entradas_incompletas():
    estado = estado_da_planta([{"id": 7, "estado": "alarme", "conformidade": 5, "incidentes_por_regra": {"r": -2}}])
    camera = estado["cameras"][0]
    assert camera["conformidade"] == 1.0
    assert camera["incidentes_por_regra"] == {"r": 0}
    assert camera["ultimo_alerta"] is None
    assert estado["torre"] == "vermelho"
    json.dumps(estado)  # tem que ser serializável como está


# -- OPC UA ----------------------------------------------------------------------


def test_opcua_publica_estado_e_cliente_le_nos_exatos(servidor_opcua):
    assert servidor_opcua.publicar(_estado_vermelho(), aguardar_s=5) is True
    with Client(servidor_opcua.endpoint, timeout=5) as cliente:
        idx = cliente.get_namespace_index("urn:visionepi")
        assert idx == servidor_opcua.indice_namespace
        assert cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value() is True
        assert cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() == "vermelho"
        base = f"ns={idx};s=Cameras.Camera_1"
        assert cliente.get_node(f"{base}.Estado").read_value() == "alarme"
        assert cliente.get_node(f"{base}.Conformidade").read_value() == pytest.approx(0.5)
        assert cliente.get_node(f"{base}.UltimoAlerta").read_value() == "Sem capacete na Linha 1"
        assert cliente.get_node(f"{base}.IncidentesAtivos.sem_capacete").read_value() == 2
        assert cliente.get_node(f"{base}.IncidentesAtivos.sem_colete").read_value() == 1
        # Mesmo nó pelo BrowsePath (é assim que um SCADA navega).
        pelo_caminho = cliente.nodes.objects.get_child(
            [f"{idx}:Cameras", f"{idx}:Camera_1", f"{idx}:IncidentesAtivos", f"{idx}:sem_capacete"]
        )
        assert pelo_caminho.read_value() == 2
        assert pelo_caminho.nodeid.to_string() == f"{base}.IncidentesAtivos.sem_capacete"
        # Tipos OPC UA declarados.
        assert cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_data_type_as_variant_type() == ua.VariantType.Boolean
        assert cliente.get_node(f"{base}.Conformidade").read_data_type_as_variant_type() == ua.VariantType.Double
        assert pelo_caminho.read_data_type_as_variant_type() == ua.VariantType.Int32


def test_opcua_estado_verde_substitui_o_de_alarme_e_zera_regras(servidor_opcua):
    assert servidor_opcua.publicar(_estado_vermelho(), aguardar_s=5)
    assert servidor_opcua.publicar(_estado_verde(), aguardar_s=5)
    with Client(servidor_opcua.endpoint, timeout=5) as cliente:
        idx = cliente.get_namespace_index("urn:visionepi")
        assert cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value() is False
        assert cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() == "verde"
        base = f"ns={idx};s=Cameras.Camera_1"
        assert cliente.get_node(f"{base}.Estado").read_value() == "ok"
        assert cliente.get_node(f"{base}.UltimoAlerta").read_value() == ""
        # Regra que sumiu do resumo não fica com o número velho: o nó continua, valendo 0.
        assert cliente.get_node(f"{base}.IncidentesAtivos.sem_capacete").read_value() == 0
        assert cliente.get_node(f"{base}.IncidentesAtivos.sem_colete").read_value() == 0


def test_opcua_camera_que_some_do_estado_fica_offline_e_conformidade_nula_vira_nan(servidor_opcua):
    sem_dado = estado_da_planta([_camera(2, "ok", conformidade=None)])
    assert servidor_opcua.publicar(estado_da_planta([_camera(1), _camera(2)]), aguardar_s=5)
    assert servidor_opcua.publicar(sem_dado, aguardar_s=5)
    with Client(servidor_opcua.endpoint, timeout=5) as cliente:
        idx = cliente.get_namespace_index("urn:visionepi")
        assert cliente.get_node(f"ns={idx};s=Cameras.Camera_1.Estado").read_value() == "offline"
        conformidade = cliente.get_node(f"ns={idx};s=Cameras.Camera_2.Conformidade").read_value()
        assert conformidade != conformidade  # NaN


def test_opcua_e_somente_leitura_para_clientes(servidor_opcua):
    assert servidor_opcua.publicar(_estado_verde(), aguardar_s=5)
    with Client(servidor_opcua.endpoint, timeout=5) as cliente:
        idx = cliente.get_namespace_index("urn:visionepi")
        no = cliente.get_node(f"ns={idx};s=Planta.Torre")
        with pytest.raises(ua.UaStatusCodeError):
            no.write_value("vermelho")
        assert no.read_value() == "verde"


def test_opcua_publicar_de_varios_threads_nao_corrompe(servidor_opcua):
    def publicador(n):
        for _ in range(5):
            servidor_opcua.publicar(estado_da_planta([_camera(n, "ok", {f"regra_{n}": n})]))

    threads = [threading.Thread(target=publicador, args=(n,)) for n in range(1, 5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert servidor_opcua.publicar(estado_da_planta([_camera(n, "ok", {f"regra_{n}": n}) for n in range(1, 5)]), aguardar_s=5)
    with Client(servidor_opcua.endpoint, timeout=5) as cliente:
        idx = cliente.get_namespace_index("urn:visionepi")
        for n in range(1, 5):
            assert cliente.get_node(f"ns={idx};s=Cameras.Camera_{n}.IncidentesAtivos.regra_{n}").read_value() == n


def test_opcua_publicar_sem_servidor_no_ar_devolve_false_sem_lancar():
    servidor = ServidorOPCUA(porta=_porta_livre())
    assert servidor.publicar(_estado_verde()) is False
    servidor.parar()  # parar sem ter iniciado também não lança


# -- MQTT ------------------------------------------------------------------------


def test_mqtt_publica_alerta_e_estado_e_estado_chega_retido_para_quem_conecta_depois(broker, assinantes):
    ao_vivo = assinantes(broker.porta)
    publicador = PublicadorMQTT("127.0.0.1", broker.porta)
    try:
        assert publicador.iniciar()["conectado"] is True
        alerta = {"mensagem": "Sem capacete na Linha 1", "severidade": "critico", "camera_id": 3, "ts": "2026-10-17T10:00:00+00:00"}
        estado = _estado_vermelho()
        assert publicador.publicar_alerta(3, alerta) is True
        assert publicador.publicar_estado(estado) is True

        recebidas = {topico: (corpo, retain) for topico, corpo, retain in ao_vivo.receber(2)}
        assert set(recebidas) == {"visionepi/3/alerta", "visionepi/planta/estado"}
        assert recebidas["visionepi/3/alerta"][0] == alerta
        assert recebidas["visionepi/planta/estado"][0] == json.loads(json.dumps(estado))
        # Entrega ao vivo não leva a flag retain; ela só vale para quem assina depois.
        assert recebidas["visionepi/3/alerta"][1] is False

        tardio = assinantes(broker.porta)
        # O amqtt 0.12.1 entrega o retido mais de uma vez (QoS 0 e QoS 1): tolera duplicata, exige o conteúdo.
        retidas = tardio.receber(1)
        assert retidas, "assinante tardio não recebeu o estado retido"
        assert all(t == "visionepi/planta/estado" and r is True and c == retidas[0][1] for t, c, r in retidas)
        assert retidas[0][1] == json.loads(json.dumps(estado))
        # Alerta é evento, não estado: nunca é retido.
        time.sleep(0.5)
        restantes = []
        while not tardio.mensagens.empty():
            restantes.append(tardio.mensagens.get_nowait()[0])
        assert "visionepi/3/alerta" not in restantes
    finally:
        publicador.parar()


def test_mqtt_sanitiza_camera_id_para_nao_virar_curinga(broker, assinantes):
    ao_vivo = assinantes(broker.porta)
    publicador = PublicadorMQTT("127.0.0.1", broker.porta, prefixo="planta-a")
    try:
        assert publicador.iniciar()["conectado"]
        assert publicador.topico_alerta("a/b#+") == "planta-a/a_b__/alerta"
        assert publicador.topico_alerta("") == "planta-a/_/alerta"
    finally:
        publicador.parar()
    assert ao_vivo.mensagens.empty()


def test_mqtt_com_broker_fora_nao_lanca_e_status_indica_desconectado():
    publicador = PublicadorMQTT("127.0.0.1", _porta_livre())
    try:
        status = publicador.iniciar(aguardar_s=0.5)
        assert status["conectado"] is False
        assert status["erro"]
        # Publicar com o broker fora: não lança nem bloqueia (a mensagem fica na fila do paho).
        inicio = time.monotonic()
        publicador.publicar_alerta(1, {"mensagem": "x"})
        publicador.publicar_estado({"torre": "verde"})
        assert time.monotonic() - inicio < 1.0
        assert publicador.status()["conectado"] is False
    finally:
        publicador.parar()


def test_mqtt_publicar_antes_de_iniciar_devolve_false():
    assert PublicadorMQTT("127.0.0.1", _porta_livre()).publicar_estado({"torre": "verde"}) is False


def test_broker_embutido_em_porta_ocupada_falha_com_mensagem_legivel():
    with socket.socket() as ocupante:
        ocupante.bind(("127.0.0.1", 0))
        ocupante.listen()
        porta = ocupante.getsockname()[1]
        status = BrokerEmbutido(porta=porta).iniciar()
    assert status["estado"] == "falhou"
    assert str(porta) in status["erro"]
    assert "Traceback" not in status["erro"]


# -- Webhook ---------------------------------------------------------------------


def _esperar_recebidos(receptor: _ReceptorHTTP, quantos: int = 1):
    _esperar(lambda: len(receptor.recebidos) >= quantos)
    return receptor.recebidos


def test_webhook_envia_post_json_para_servidor_local_quando_rede_local_permitida(receptor_http):
    webhook = Webhook(receptor_http.url("/hook?token=abc"), timeout_s=3, permitir_rede_local=True)
    try:
        assert webhook.enviar({"tipo": "alerta", "mensagem": "Sem capacete ç"}) is True
        recebidos = _esperar_recebidos(receptor_http)
    finally:
        webhook.parar()
    assert recebidos[0]["json"] == {"tipo": "alerta", "mensagem": "Sem capacete ç"}
    assert recebidos[0]["tipo"].startswith("application/json")
    assert recebidos[0]["caminho"] == "/hook?token=abc"
    assert webhook.estatisticas()["enviados"] == 1
    assert "token" not in webhook.endpoint  # a query (onde costuma ir o segredo) não aparece em status/log


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/",
        "http://localhost/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://169.254.169.254/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://[fe80::1]/",
        "http://10.0.0.1",
        "http://172.16.5.4/",
        "http://192.168.1.10:8080/hook",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "file:///etc/passwd",
        "ftp://exemplo.com/",
        "gopher://exemplo.com/",
        "javascript:alert(1)",
        "http://",
        "",
        "http://usuario:senha@93.184.216.34/",
    ],
)
def test_webhook_rejeita_destinos_perigosos_por_padrao(url):
    with pytest.raises(UrlWebhookInvalida):
        Webhook(url, permitir_rede_local=False)


@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/", "http://[fe80::1]/", "http://0.0.0.0/", "http://224.0.0.1/", "http://[fd00:ec2::254]/", "file:///x"],
)
def test_webhook_nunca_libera_metadados_multicast_ou_nao_especificado_nem_com_rede_local(url):
    with pytest.raises(UrlWebhookInvalida):
        Webhook(url, permitir_rede_local=True)


@pytest.mark.parametrize("url", ["http://10.0.0.1/hook", "http://192.168.1.10:8080/hook", "http://127.0.0.1:9/", "http://[::1]/"])
def test_webhook_aceita_rede_local_so_com_flag_explicita(url):
    assert Webhook(url, permitir_rede_local=True).endpoint


@pytest.mark.parametrize("url", ["http://93.184.216.34/hook", "https://93.184.216.34:8443/hook"])
def test_webhook_aceita_destino_publico_sem_flag(url):
    assert Webhook(url).endpoint.startswith(url.split("/hook")[0])


def test_webhook_nao_segue_redirecionamento(receptor_http):
    webhook = Webhook(receptor_http.url("/redireciona"), permitir_rede_local=True)
    try:
        webhook.enviar({"n": 1})
        _esperar(lambda: webhook.estatisticas()["falhas"] >= 1)
    finally:
        webhook.parar()
    assert [r["caminho"] for r in receptor_http.recebidos] == ["/redireciona"]  # o /destino nunca foi visitado
    assert "302" in webhook.estatisticas()["ultimo_erro"]


def test_webhook_revalida_o_destino_a_cada_envio_contra_dns_rebinding(receptor_http):
    respostas = iter([["93.184.216.34"]])  # na criação o nome aponta para um IP público...

    def resolvedor(host, porta):
        return next(respostas, ["127.0.0.1"])  # ...e depois muda para o loopback

    webhook = Webhook(f"http://exemplo.test:{receptor_http.porta}/hook", resolver=resolvedor)
    try:
        webhook.enviar({"n": 1})
        _esperar(lambda: webhook.estatisticas()["falhas"] >= 1)
    finally:
        webhook.parar()
    assert receptor_http.recebidos == []
    assert "bloqueado" in webhook.estatisticas()["ultimo_erro"].lower()


def test_webhook_conecta_no_ip_validado_e_nao_no_nome(receptor_http):
    webhook = Webhook(
        f"http://exemplo.test:{receptor_http.porta}/hook", permitir_rede_local=True, resolver=lambda host, porta: ["127.0.0.1"]
    )
    try:
        webhook.enviar({"n": 1})
        recebidos = _esperar_recebidos(receptor_http)
    finally:
        webhook.parar()
    assert recebidos[0]["json"] == {"n": 1}


def test_webhook_fila_cheia_descarta_o_mais_antigo(receptor_http, monkeypatch):
    webhook = Webhook(receptor_http.url(), permitir_rede_local=True, tamanho_fila=2)
    monkeypatch.setattr(webhook, "iniciar", lambda: None)  # sem consumidor: a fila só enche
    for n in range(1, 5):
        assert webhook.enviar({"n": n}) is True
    estatisticas = webhook.estatisticas()
    assert estatisticas["pendentes"] == 2
    assert estatisticas["descartados"] == 2
    monkeypatch.undo()
    try:
        webhook.iniciar()
        recebidos = _esperar_recebidos(receptor_http, 2)
    finally:
        webhook.parar()
    assert [r["json"]["n"] for r in recebidos] == [3, 4]


def test_webhook_destino_fora_do_ar_conta_falha_sem_lancar():
    webhook = Webhook(f"http://127.0.0.1:{_porta_livre()}/hook", timeout_s=1, permitir_rede_local=True)
    try:
        assert webhook.enviar({"n": 1}) is True
        _esperar(lambda: webhook.estatisticas()["falhas"] >= 1)
    finally:
        webhook.parar()
    assert webhook.estatisticas()["falhas"] == 1
    assert webhook.estatisticas()["ultimo_erro"]


# -- Gerente: degradação e fluxo completo --------------------------------------------


def test_gerente_com_tudo_desligado_nao_sobe_nada():
    gerente = GerenteDeIntegracao({})
    try:
        status = gerente.iniciar()
        assert {k: v["estado"] for k, v in status.items()} == {
            "opcua": "desligado",
            "mqtt": "desligado",
            "broker": "desligado",
            "webhook": "desligado",
        }
        assert all(v["ativo"] is False for v in status.values())
        assert gerente.publicar_estado(_estado_verde()) is True  # sem destino, mas não quebra
        assert gerente.publicar_alerta(1, {"mensagem": "x"}) is False
    finally:
        gerente.parar()


def test_gerente_porta_opcua_ocupada_vira_status_falhou_sem_excecao():
    with socket.socket() as ocupante:
        ocupante.bind(("127.0.0.1", 0))
        ocupante.listen()
        porta = ocupante.getsockname()[1]
        gerente = GerenteDeIntegracao({"OPCUA_ATIVO": True, "OPCUA_PORTA": porta})
        try:
            status = gerente.iniciar()
            opcua = status["opcua"]
            assert opcua["ativo"] is True
            assert opcua["estado"] == "falhou"
            assert opcua["endpoint"] == f"opc.tcp://127.0.0.1:{porta}/visionepi/"
            assert str(porta) in opcua["erro"] and "porta" in opcua["erro"].lower()
            assert "Traceback" not in opcua["erro"]
            assert status["mqtt"]["estado"] == "desligado"
            # Com o OPC UA fora, publicar continua seguro.
            assert gerente.publicar_estado(_estado_vermelho()) is True
        finally:
            gerente.parar()


def test_gerente_broker_mqtt_fora_vira_falhou_e_nao_lanca_ao_publicar():
    porta = _porta_livre()
    gerente = GerenteDeIntegracao({"MQTT_ATIVO": "true", "MQTT_HOST": "127.0.0.1", "MQTT_PORTA": str(porta)})
    try:
        status = gerente.iniciar()
        assert status["mqtt"]["ativo"] is True
        assert status["mqtt"]["estado"] == "falhou"
        assert status["mqtt"]["erro"]
        assert gerente.publicar_estado(_estado_vermelho()) is True
        gerente.publicar_alerta(1, {"mensagem": "x"})
    finally:
        gerente.parar()


@pytest.mark.parametrize("porta", ["abc", "0", "70000"])
def test_gerente_porta_invalida_vira_falhou_com_mensagem(porta):
    gerente = GerenteDeIntegracao({"OPCUA_ATIVO": True, "OPCUA_PORTA": porta})
    try:
        opcua = gerente.iniciar()["opcua"]
        assert opcua["estado"] == "falhou"
        assert "OPCUA_PORTA" in opcua["erro"]
    finally:
        gerente.parar()


def test_gerente_webhook_com_url_perigosa_e_rejeitado_no_status():
    gerente = GerenteDeIntegracao({"WEBHOOK_URL": "http://169.254.169.254/latest/meta-data/"})
    try:
        webhook = gerente.iniciar()["webhook"]
        assert webhook["estado"] == "falhou"
        assert "WEBHOOK_URL" in webhook["erro"]
        assert gerente.publicar_alerta(1, {"mensagem": "x"}) is False
    finally:
        gerente.parar()


def test_gerente_deduplica_estado_e_republica_a_cada_5_segundos():
    relogio = [100.0]
    gerente = GerenteDeIntegracao({}, relogio=lambda: relogio[0])
    try:
        gerente.iniciar()
        assert gerente.publicar_estado(_estado_vermelho()) is True
        relogio[0] += 1
        igual_com_outro_ts = {**_estado_vermelho(), "ts": "outro-instante"}
        assert gerente.publicar_estado(igual_com_outro_ts) is False  # só o ts mudou
        assert gerente.publicar_estado(_estado_verde()) is True  # mudou de verdade
        relogio[0] += 4.9
        assert gerente.publicar_estado(_estado_verde()) is False
        relogio[0] += 0.2
        assert gerente.publicar_estado(_estado_verde()) is True  # passou de 5 s: reenvio periódico
    finally:
        gerente.parar()


def test_gerente_fluxo_completo_opcua_mqtt_broker_e_webhook(receptor_http, assinantes):
    porta_opcua, porta_mqtt = _porta_livre(), _porta_livre()
    gerente = GerenteDeIntegracao(
        {
            "OPCUA_ATIVO": True,
            "OPCUA_PORTA": porta_opcua,
            "MQTT_ATIVO": True,
            "MQTT_BROKER_EMBUTIDO": True,
            "MQTT_PORTA": porta_mqtt,
            "WEBHOOK_URL": receptor_http.url("/alertas"),
            "WEBHOOK_PERMITIR_REDE_LOCAL": True,
        },
        agora=lambda: datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc),
    )
    try:
        status = gerente.iniciar()
        assert {k: v["estado"] for k, v in status.items()} == {
            "opcua": "no_ar",
            "mqtt": "no_ar",
            "broker": "no_ar",
            "webhook": "no_ar",
        }
        assert status["opcua"]["endpoint"] == f"opc.tcp://127.0.0.1:{porta_opcua}/visionepi/"
        assert status["broker"]["endpoint"] == f"mqtt://127.0.0.1:{porta_mqtt}"

        ao_vivo = assinantes(porta_mqtt)
        estado = _estado_vermelho()
        alerta = {"mensagem": "Sem capacete na Linha 1", "severidade": "critico"}
        assert gerente.publicar_estado(estado) is True
        assert gerente.publicar_alerta(1, alerta) is True

        recebidas = {topico: corpo for topico, corpo, _ in ao_vivo.receber(2)}
        assert recebidas["visionepi/planta/estado"]["torre"] == "vermelho"
        assert recebidas["visionepi/1/alerta"] == alerta

        webhooks = _esperar_recebidos(receptor_http)
        assert webhooks[0]["caminho"] == "/alertas"
        assert webhooks[0]["json"] == {
            "tipo": "alerta",
            "camera_id": 1,
            "alerta": alerta,
            "ts": "2026-10-17T12:00:00+00:00",
        }

        with Client(f"opc.tcp://127.0.0.1:{porta_opcua}/visionepi/", timeout=5) as cliente:
            idx = cliente.get_namespace_index("urn:visionepi")
            torre = cliente.get_node(f"ns={idx};s=Planta.Torre")
            assert _esperar(lambda: torre.read_value() == "vermelho")
            assert cliente.get_node(f"ns={idx};s=Cameras.Camera_1.IncidentesAtivos.sem_capacete").read_value() == 2
    finally:
        gerente.parar()
    assert gerente.status()["opcua"]["estado"] == "desligado"
