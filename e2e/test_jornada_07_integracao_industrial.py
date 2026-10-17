"""Jornada 7 (MISSÃO 4, Fase 5 item 3): a integração industrial, do alerta à torre de luz e à sirene.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py), com OPC UA e MQTT (broker embutido) ligados
em portas livres e lidos por clientes REAIS (asyncua e paho):

1. um alerta crítico na Multidão chega ao nó OPC UA `Planta.PlantaEmAlarme`, ao tópico MQTT
   `visionepi/planta/estado` (retido) e à torre vermelha da tela `/torre`;
2. reconhecer ("avisei o colaborador") marca os alertas no MESMO estado que alimenta a sirene: os reconhecidos
   deixam de contar e a sirene da câmera cala quando não há crítico novo, mas a torre CONTINUA vermelha
   (reconhecer não apaga a violação);
3. a torre só deixa de ser vermelha quando a violação acaba: a Multidão é parada pela API (o operador, que só
   enxerga a própria câmera, vê a torre dele sair do vermelho por causa dela; o nó OPC UA da câmera vai a
   `offline`) e, ao religar a câmera, a violação volta e a torre também.
   (A câmera parada fica "offline", que a torre pinta de amarelo: parar a câmera não é prova de conformidade.)

Timeouts generosos para esta máquina lenta: servidor com OPC UA/MQTT 120 s; primeiro alarme até 300 s;
a sirene calar 90 s; parar/religar a câmera 60 s e 300 s.
Movida e ajustada de e2e/test_missao4.py (M2).
"""

from __future__ import annotations

import json
import threading
import time

from conftest import alertas_ativos, entrar, esperar, registrar_tempo


def _planta_do_operador(operador, servidor) -> dict:
    """A planta como o OPERADOR a vê: só a câmera dele (o estado é recalculado só com ela)."""
    return operador.get(f"{servidor.base}/api/integracao/estado", timeout=20).json()["planta"]


def test_alerta_chega_no_opcua_no_mqtt_e_na_torre_e_reconhecer_cala_a_sirene(pagina, servidor):
    import paho.mqtt.client as mqtt
    from asyncua.sync import Client

    supervisor = servidor.sessao("supervisor")
    operador = servidor.sessao("operator")
    multidao = servidor.cameras["Multidão"]
    estado = esperar(lambda: (r := supervisor.get(f"{servidor.base}/api/integracao/estado", timeout=20).json())
                     ["integracoes"]["opcua"]["estado"] == "no_ar" and r, 120, msg="OPC UA não subiu no servidor")
    assert estado["integracoes"]["broker"]["estado"] == "no_ar", estado["integracoes"]

    recebidos: list[tuple[str, dict]] = []
    chegou_estado = threading.Event()
    assinante = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def ao_receber(_c, _u, msg):
        try:
            corpo = json.loads(msg.payload)
        except ValueError:
            return
        recebidos.append((msg.topic, corpo))
        if msg.topic == "visionepi/planta/estado" and corpo.get("torre") == "vermelho":
            chegou_estado.set()

    assinante.on_message = ao_receber
    assinante.connect("127.0.0.1", servidor.porta_mqtt)
    assinante.subscribe("visionepi/#", qos=1)
    assinante.loop_start()
    cliente = Client(f"opc.tcp://127.0.0.1:{servidor.porta_opcua}/visionepi/")
    cliente.connect()
    try:
        idx = cliente.get_namespace_index("urn:visionepi")
        inicio = time.monotonic()
        esperar(lambda: cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value() is True, 300,
                msg="PlantaEmAlarme não ficou True (Multidão tem gente sem capacete)")
        registrar_tempo("m2_ate_planta_em_alarme", time.monotonic() - inicio)
        assert cliente.get_node(f"ns={idx};s=Planta.Torre").read_value() == "vermelho"
        estado_cam = cliente.get_node(f"ns={idx};s=Cameras.Camera_{multidao}.Estado").read_value()
        assert estado_cam == "alarme", estado_cam
        assert chegou_estado.wait(30), [t for t, _ in recebidos][:20]
        alertas_mqtt = [c for t, c in recebidos if t.endswith("/alerta")]
        # Pode não haver alerta NOVO depois da assinatura se todos nasceram antes; o estado retido é a garantia.
        if alertas_mqtt:
            assert {"id", "regra", "severidade", "mensagem"} <= set(alertas_mqtt[0])

        # A torre na tela reflete o mesmo estado.
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        pagina.goto(servidor.base + "/torre")
        torre = pagina.locator("[data-testid=torre]")
        torre.wait_for(timeout=60_000)
        assert torre.get_attribute("data-cor") == "vermelho"

        # Reconhecer ("avisei o colaborador") marca o alerta como reconhecido no MESMO estado que
        # alimenta a sirene. A Multidão gera alertas críticos novos a cada pessoa nova, então a
        # sirene pode voltar; o que se verifica é que os reconhecidos deixam de contar.
        criticos = [a for a in alertas_ativos(supervisor, servidor, "Multidão") if a.get("severity") == "critical"]
        assert criticos, "Multidão sem alerta crítico ativo"
        for a in criticos:
            assert supervisor.post(f"{servidor.base}/alerts/{a['id']}/acknowledge", json={"note": "e2e"},
                                   timeout=20).status_code == 200
        reconhecidos = {a["id"] for a in criticos}

        def reconhecidos_no_estado() -> bool:
            ativos = {a["id"]: a for a in alertas_ativos(supervisor, servidor, "Multidão")}
            return all(ativos[i].get("acknowledged") for i in reconhecidos if i in ativos)

        esperar(reconhecidos_no_estado, 60, msg="alertas reconhecidos não apareceram como reconhecidos no estado")

        # A sirene da câmera cala quando não há crítico novo: o operador reconhece tudo ("Avisei todos") até pegar um
        # instante com crítico ativo e nenhum sem reconhecer. A torre segue VERMELHA: reconhecer não apaga a violação.
        def sirene_calada():
            assert operador.post(f"{servidor.base}/alerts/acknowledge-all", json={"note": "e2e"}, timeout=20).status_code == 200
            planta = _planta_do_operador(operador, servidor)
            camera = next((c for c in planta["cameras"] if c["id"] == multidao), None)
            return bool(camera) and camera["incidentes_criticos"] > 0 and not planta["sirene"] and (planta, camera)

        planta, camera = esperar(sirene_calada, 90, 1, msg="a sirene da Multidão não calou depois de reconhecer tudo")
        assert planta["torre"] == "vermelho", planta
        assert camera["critico_nao_reconhecido"] is False, camera
        pagina.reload()
        pagina.locator("[data-testid=torre]").wait_for(timeout=60_000)
    finally:
        cliente.disconnect()
        assinante.loop_stop()
        assinante.disconnect()


def test_torre_so_deixa_o_vermelho_quando_a_violacao_acaba(servidor):
    from asyncua.sync import Client

    tecnico = servidor.sessao("technical")
    operador = servidor.sessao("operator")
    multidao = servidor.cameras["Multidão"]
    esperar(lambda: _planta_do_operador(operador, servidor)["torre"] == "vermelho", 300,
            msg="a torre do operador não ficou vermelha com a Multidão violando")

    cliente = Client(f"opc.tcp://127.0.0.1:{servidor.porta_opcua}/visionepi/")
    cliente.connect()
    try:
        idx = cliente.get_namespace_index("urn:visionepi")
        tecnico.post(f"{servidor.base}/api/cameras/{multidao}/stop", timeout=60).raise_for_status()
        try:
            # Sem a câmera analisando não há violação: a torre do operador (só a Multidão) sai do vermelho.
            planta = esperar(lambda: (p := _planta_do_operador(operador, servidor))["torre"] != "vermelho" and p, 60, 1,
                             msg="a torre do operador continuou vermelha com a Multidão parada")
            assert planta["sirene"] is False and planta["planta_em_alarme"] is False, planta
            for camera in planta["cameras"]:
                assert camera["incidentes_criticos"] == 0 and camera["estado"] == "offline", camera
            esperar(lambda: cliente.get_node(f"ns={idx};s=Cameras.Camera_{multidao}.Estado").read_value() == "offline", 60, 1,
                    msg="o nó OPC UA da câmera não foi a offline")
        finally:
            tecnico.post(f"{servidor.base}/api/cameras/{multidao}/start", timeout=60).raise_for_status()
        # Religada, a câmera volta a analisar, a violação volta e a torre também.
        esperar(lambda: _planta_do_operador(operador, servidor)["torre"] == "vermelho", 300, 2,
                msg="a torre do operador não voltou a vermelho com a Multidão religada")
    finally:
        cliente.disconnect()
