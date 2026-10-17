"""E2E da MISSÃO 4 — Fábrica conectada (M1 a M5) contra o servidor REAL com 4 câmeras.

M1 sabotagem: a fonte MJPEG passa a servir quadros tampados no meio do teste.
M2 integração: clientes OPC UA (asyncua) e MQTT (paho) reais leem o alerta.
M3 evacuação: acionar, contar, encerrar e conferir o elo na custódia, pela tela.
M4 editor de regras: regra criada na API, testada no histórico e disparando ao vivo.
M5 permissão de trabalho: sem vigia → alerta crítico; com vigia → sem alerta.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from conftest import RAIZ, entrar

TEMPOS = RAIZ / "bench" / "runtime" / "missao4-tempos.jsonl"


def _registrar(medida: str, segundos: float, **extra) -> None:
    TEMPOS.parent.mkdir(parents=True, exist_ok=True)
    with TEMPOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"medida": medida, "segundos": round(segundos, 1), "ts": time.time(), **extra}) + "\n")


def _esperar(condicao, limite_s: float, passo_s: float = 1.0, msg: str = ""):
    fim = time.monotonic() + limite_s
    ultimo = None
    while time.monotonic() < fim:
        ultimo = condicao()
        if ultimo:
            return ultimo
        time.sleep(passo_s)
    raise AssertionError(f"tempo esgotado ({limite_s:g} s): {msg} — último valor: {ultimo!r}")


def _alertas(sessao, servidor, camera: str) -> list[dict]:
    cid = servidor.cameras[camera]
    return sessao.get(f"{servidor.base}/api/cameras/{cid}/status", timeout=20).json().get("active_alerts") or []


# --------------------------------------------------------------- M1 sabotagem
def test_m1_tampar_a_camera_alerta_e_recupera(pagina, servidor):
    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Rede"]
    url = f"{servidor.base}/api/cameras/{cid}/saude-visual"
    _esperar(lambda: (r := tecnico.get(url, timeout=20).json()).get("tem_referencia") and r.get("estado") == "ok" and r,
             180, msg="a câmera Rede não ficou com referência e estado ok")
    servidor.fonte_rede.tampar()
    inicio = time.monotonic()
    try:
        _esperar(lambda: tecnico.get(url, timeout=20).json().get("estado") == "obstruida", 90, 0.5,
                 msg="saúde visual não acusou OBSTRUÍDA")
        t_estado = time.monotonic() - inicio
        _esperar(lambda: any(a.get("rule") == "camera_obstruida" for a in _alertas(tecnico, servidor, "Rede")), 120, 0.5,
                 msg="alerta camera_obstruida não nasceu")
        t_alerta = time.monotonic() - inicio
        _registrar("m1_tampar_ate_estado", t_estado)
        _registrar("m1_tampar_ate_alerta", t_alerta)
        # A tela mostra o badge no cartão da câmera.
        entrar(pagina, servidor, "technical")
        badge = pagina.locator("[data-testid=saude-badge][data-estado=obstruida]")
        badge.first.wait_for(timeout=60_000)
        assert "OBSTRU" in badge.first.inner_text().upper()
    finally:
        servidor.fonte_rede.destampar()
    _esperar(lambda: tecnico.get(url, timeout=20).json().get("estado") == "ok", 120, msg="não voltou a OK ao destampar")
    _esperar(lambda: not any(a.get("rule") == "camera_obstruida" for a in _alertas(tecnico, servidor, "Rede")), 180,
             msg="alerta camera_obstruida não resolveu ao destampar")


def test_m1_redefinir_referencia_so_tecnico(servidor):
    cid = servidor.cameras["Canteiro"]
    url = f"{servidor.base}/api/cameras/{cid}/saude-visual/referencia"
    assert servidor.sessao("operator").post(url, timeout=20).status_code in (403, 404)
    r = servidor.sessao("technical").post(url, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["tem_referencia"] is True and r.json()["estado"] == "ok"


# ------------------------------------------------------------- M2 integração
def test_m2_alerta_chega_no_opcua_no_mqtt_e_na_torre(pagina, servidor):
    import paho.mqtt.client as mqtt
    from asyncua.sync import Client

    supervisor = servidor.sessao("supervisor")
    estado = _esperar(lambda: (r := supervisor.get(f"{servidor.base}/api/integracao/estado", timeout=20).json())
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
        multidao = servidor.cameras["Multidão"]
        inicio = time.monotonic()
        _esperar(lambda: cliente.get_node(f"ns={idx};s=Planta.PlantaEmAlarme").read_value() is True, 300,
                 msg="PlantaEmAlarme não ficou True (Multidão tem gente sem capacete)")
        _registrar("m2_ate_planta_em_alarme", time.monotonic() - inicio)
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
        criticos = [a for a in _alertas(supervisor, servidor, "Multidão") if a.get("severity") == "critical"]
        assert criticos, "Multidão sem alerta crítico ativo"
        for a in criticos:
            assert supervisor.post(f"{servidor.base}/alerts/{a['id']}/acknowledge", json={"note": "e2e"},
                                   timeout=20).status_code == 200
        reconhecidos = {a["id"] for a in criticos}

        def reconhecidos_no_estado() -> bool:
            ativos = {a["id"]: a for a in _alertas(supervisor, servidor, "Multidão")}
            return all(ativos[i].get("acknowledged") for i in reconhecidos if i in ativos)

        _esperar(reconhecidos_no_estado, 60, msg="alertas reconhecidos não apareceram como reconhecidos no estado")
    finally:
        cliente.disconnect()
        assinante.loop_stop()
        assinante.disconnect()


def test_m2_operador_ve_so_a_propria_camera_na_torre(servidor):
    corpo = servidor.sessao("operator").get(f"{servidor.base}/api/integracao/estado", timeout=20).json()
    ids = {c["id"] for c in corpo["planta"]["cameras"]}
    assert ids <= {servidor.cameras["Multidão"]}, ids


# --------------------------------------------------------------- M3 evacuação
def test_m3_evacuacao_pela_tela_ate_o_relatorio_na_custodia(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        pagina.goto(servidor.base + "/evacuacao")
        raiz = pagina.locator("[data-testid=evacuacao]")
        raiz.wait_for(timeout=60_000)
        assert "dupla contagem" in pagina.locator("[data-testid=evac-aviso]").inner_text()
        pagina.get_by_label("Câmera do ponto de encontro").select_option(str(servidor.cameras["Canteiro"]))
        pagina.get_by_role("button", name="Acionar evacuação").click()
        pagina.get_by_role("button", name="Acionar agora").click()
        pagina.locator("[data-testid=evacuacao][data-ativa='1']").wait_for(timeout=30_000)
        crono = pagina.locator("[data-testid=evac-cronometro]")
        primeiro = crono.inner_text()
        time.sleep(3)
        assert crono.inner_text() != primeiro, "o cronômetro não anda"
        assert "dupla contagem" in pagina.locator("[data-testid=evac-aviso]").inner_text()
        assert int(pagina.locator("[data-testid=evac-total]").inner_text().strip() or 0) >= 0
        pagina.get_by_role("button", name="Encerrar evacuação").click()
        pagina.get_by_role("button", name="Encerrar e salvar relatório").click()
        custodia = pagina.locator("[data-testid=evac-custodia]")
        custodia.wait_for(timeout=30_000)
        assert "cadeia de custódia" in custodia.inner_text()
    finally:
        contexto.close()
    tecnico = servidor.sessao("technical")
    elos = tecnico.get(f"{servidor.base}/api/custodia?limit=50", timeout=20).json()["items"]
    assert any(e.get("tipo") == "evacuacao" for e in elos), [e.get("tipo") for e in elos][:10]
    verificacao = tecnico.get(f"{servidor.base}/api/custodia/verificar", timeout=60).json()
    assert verificacao.get("integra") is True, verificacao


def test_m3_operador_nao_aciona(servidor):
    assert servidor.sessao("operator").post(f"{servidor.base}/api/evacuacao/iniciar", json={}, timeout=20).status_code == 403
    assert servidor.sessao("technical").post(f"{servidor.base}/api/evacuacao/iniciar", json={}, timeout=20).status_code == 403


# ------------------------------------------------------------ M4 editor de regras
def test_m4_regra_do_editor_testada_no_historico_e_disparando_ao_vivo(navegador, servidor):
    tecnico = servidor.sessao("technical")
    multidao = servidor.cameras["Multidão"]
    regra = {
        "nome": "E2E: sem capacete por 2 s",
        "camera_ids": [multidao],
        "condicao": {"op": "E", "itens": [{"tipo": "epi", "epi": "helmet", "estado": "ausente"},
                                          {"tipo": "duracao", "segundos": 2}]},
        "acoes": {"severidade": "high", "mensagem": "Regra E2E: sem capacete", "fala": False, "integracao": True,
                  "escalonamento": {"supervisor_s": None, "tv_s": None}},
    }
    # Testar no histórico antes de ativar (trilhas gravadas pelo X2).
    teste = _esperar(lambda: (r := tecnico.post(f"{servidor.base}/api/regras/testar",
                                                json={"regra": regra, "camera_id": multidao, "horas": 1}, timeout=60))
                     .status_code == 200 and r.json(), 180, 3, msg="teste no histórico não respondeu 200")
    assert teste["simulavel"] is True, teste
    assert teste["disparos"] >= 1, teste
    criada = tecnico.post(f"{servidor.base}/api/regras", json=regra, timeout=20)
    assert criada.status_code == 201, criada.text
    rid = criada.json()["regra"]["id"]
    try:
        assert tecnico.post(f"{servidor.base}/api/regras/{rid}/ativar", timeout=20).status_code == 200
        _esperar(lambda: any(a.get("rule") == f"regra:{rid}" for a in _alertas(tecnico, servidor, "Multidão")), 240,
                 msg="a regra do editor não gerou alerta ao vivo")
        # A tela lista a regra.
        contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
        try:
            pagina = contexto.new_page()
            entrar(pagina, servidor, "technical")
            pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
            pagina.goto(servidor.base + "/regras")
            pagina.locator("[data-testid=regras-lista]").wait_for(timeout=60_000)
            assert "E2E: sem capacete" in pagina.locator("[data-testid=regras-lista]").inner_text()
        finally:
            contexto.close()
    finally:
        tecnico.delete(f"{servidor.base}/api/regras/{rid}", timeout=20)


# ------------------------------------------------------- M5 permissão de trabalho
def test_m5_permissao_com_vigia(servidor):
    """Zona = quadro inteiro da Multidão. Área do vigia num canto vazio → sem vigia (crítico).
    Nova permissão com a área do vigia cobrindo quem está na cena → quem está nela é vigia, sem alerta."""
    from datetime import datetime, timedelta, timezone

    tecnico = servidor.sessao("technical")
    cid = servidor.cameras["Multidão"]
    zona_antes = tecnico.get(f"{servidor.base}/api/cameras/{cid}/risk-area", timeout=20).json()
    tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area",
                json={"polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], "name": "Espaço confinado E2E"}, timeout=20)
    agora = datetime.now(timezone.utc)
    base = {"camera_id": cid, "tipo": "espaco_confinado", "descricao": "Inspeção E2E", "responsavel": "Equipe E2E",
            "inicio": (agora - timedelta(minutes=1)).isoformat(), "fim": (agora + timedelta(hours=1)).isoformat(),
            "epis_exigidos": [], "exige_vigia": True}
    ids: list[int] = []
    try:
        sem_vigia = tecnico.post(f"{servidor.base}/api/permissoes",
                                 json=base | {"area_vigia": [[0.0, 0.0], [0.03, 0.0], [0.03, 0.03]]}, timeout=20)
        assert sem_vigia.status_code == 201, sem_vigia.text
        ids.append(sem_vigia.json()["id"])
        assert "33.3.4.1" in json.dumps(sem_vigia.json().get("norma"), ensure_ascii=False)
        _esperar(lambda: any(a.get("rule") == "sem_vigia" and a.get("severity") == "critical"
                             for a in _alertas(tecnico, servidor, "Multidão")), 240, msg="alerta sem_vigia não nasceu")
        assert tecnico.post(f"{servidor.base}/api/permissoes/{ids[-1]}/encerrar", timeout=20).status_code == 200
        com_vigia = tecnico.post(f"{servidor.base}/api/permissoes",
                                 json=base | {"area_vigia": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]}, timeout=20)
        assert com_vigia.status_code == 201, com_vigia.text
        ids.append(com_vigia.json()["id"])
        _esperar(lambda: not any(a.get("rule") == "sem_vigia" for a in _alertas(tecnico, servidor, "Multidão")), 240,
                 msg="sem_vigia continuou com vigia na área")
    finally:
        for pid in ids:
            tecnico.post(f"{servidor.base}/api/permissoes/{pid}/encerrar", timeout=20)
        if zona_antes.get("polygon"):
            tecnico.put(f"{servidor.base}/api/cameras/{cid}/risk-area",
                        json={"polygon": zona_antes["polygon"], "name": zona_antes.get("name") or "Área de risco"}, timeout=20)


def test_m5_operador_le_mas_nao_emite(servidor):
    operador = servidor.sessao("operator")
    assert operador.get(f"{servidor.base}/api/permissoes", timeout=20).status_code == 200
    assert operador.post(f"{servidor.base}/api/permissoes", json={}, timeout=20).status_code == 403


@pytest.mark.parametrize("rota", ["/evacuacao", "/torre", "/regras", "/permissoes"])
def test_rotas_novas_abrem_sem_erro_de_console(pagina, servidor, rota):
    entrar(pagina, servidor, "supervisor")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + rota)
    pagina.wait_for_timeout(4000)
    assert pagina.locator("main#conteudo").inner_text().strip(), f"{rota} abriu vazia"
    assert not [e for e in pagina.erros_console if "favicon" not in e], pagina.erros_console


# ------------------------------------------------- Fase 3 item 9: exceções
def test_404_desenhada(pagina, servidor):
    resposta = pagina.goto(servidor.base + "/nao-existe-mesmo")
    assert resposta.status == 404
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/nao-existe-mesmo")
    pagina.get_by_role("heading", name="Esta página não existe").wait_for(timeout=30_000)
    assert "/nao-existe-mesmo" in pagina.locator("main#conteudo").inner_text()
    import requests

    api = requests.get(servidor.base + "/api/nao-existe", timeout=10)
    assert api.status_code == 404 and api.headers["Content-Type"].startswith("application/json")


def test_sessao_expirada_volta_para_onde_estava(pagina, servidor):
    """A sessão morre por fora (cookie apagado); a tela de evacuação consulta a API a cada 5 s, recebe 401,
    o login aparece com o aviso e, depois de entrar, a pessoa volta para a mesma tela."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/evacuacao")
    pagina.locator("[data-testid=evacuacao]").wait_for(timeout=60_000)
    pagina.context.clear_cookies()
    pagina.locator("[data-testid=sessao-expirada]").wait_for(timeout=30_000)
    pagina.get_by_label("E-mail").fill(servidor.emails["technical"])
    pagina.get_by_label("Senha").fill(servidor.senhas["technical"])
    pagina.get_by_role("button", name="Entrar").click()
    pagina.wait_for_url("**/evacuacao", timeout=60_000)
    pagina.locator("[data-testid=evacuacao]").wait_for(timeout=60_000)


def test_sem_conexao_aparece_e_some(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        faixa = pagina.locator("[data-testid=sem-conexao]")
        contexto.set_offline(True)
        _esperar(lambda: "sem rede" in faixa.inner_text().lower(), 15, 0.5, msg="faixa de sem conexão não apareceu")
        contexto.set_offline(False)
        _esperar(lambda: not faixa.inner_text().strip(), 60, 1, msg="faixa de sem conexão não sumiu")
    finally:
        contexto.close()


# ---------------------------------------- Fase 3 item 2: primeiro acesso
def test_primeiro_acesso_do_supervisor_ate_pronto_para_operar(navegador, servidor):
    """Jornada 1 (MISSÃO 4): assistente do início ao checklist "pronto para operar", com a conta criada
    no passo de usuários e a senha temporária exibida uma única vez."""
    supervisor = servidor.sessao("supervisor")
    supervisor.post(f"{servidor.base}/api/onboarding/refazer", timeout=20)
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        pagina.goto(servidor.base + "/primeiro-acesso")
        pagina.locator("[data-testid=onboarding][data-concluido='0']").wait_for(timeout=60_000)
        pagina.locator("[data-testid=onb-progresso]").wait_for(timeout=10_000)
        vistos: list[str] = []
        for _ in range(12):
            passo = pagina.locator("[data-testid=onb-passo]")
            passo.wait_for(timeout=30_000)
            nome = passo.get_attribute("data-passo")
            vistos.append(nome)
            if nome == "usuarios":
                email = f"operador.onb.{int(time.time())}@e2e.local"
                pagina.get_by_label("Nome", exact=True).fill("Operador do primeiro acesso")
                pagina.get_by_label("E-mail (login)", exact=True).fill(email)
                pagina.locator("form.onb-form select").nth(0).select_option("operator")
                pagina.locator("form.onb-form select").nth(1).select_option(str(servidor.cameras["Multidão"]))
                pagina.locator("form.onb-form button[type=submit]").click()
                senha = pagina.locator("[data-testid=onb-senha-valor]")
                senha.wait_for(timeout=30_000)
                valor = senha.inner_text().strip()
                assert len(valor) >= 12
                # Não aparece em lugar nenhum da API depois.
                assert valor not in supervisor.get(f"{servidor.base}/api/users", timeout=20).text
            if nome == "pronto":
                pagina.locator("[data-testid=onb-pronto]").wait_for(timeout=30_000)
                pagina.locator("[data-testid=onb-feito]").click()
                break
            pagina.locator("[data-testid=onb-feito]").click()
            _esperar(lambda n=nome: pagina.locator("[data-testid=onb-passo]").get_attribute("data-passo") != n
                     or pagina.locator("[data-testid=onb-concluido]").count() > 0, 30, 0.5, msg=f"passo {nome} não avançou")
        pagina.locator("[data-testid=onb-concluido]").wait_for(timeout=30_000)
        # O assistente retoma no primeiro passo PENDENTE: câmera e referência já são detectadas no E2E.
        assert vistos[-1] == "pronto" and "usuarios" in vistos and "camera" not in vistos, vistos
        estado = supervisor.get(f"{servidor.base}/api/onboarding", timeout=20).json()
        assert estado["concluido"] is True
        # O checklist só marca ✓ no que foi DETECTADO (câmeras e contas existem no E2E).
        itens = {i.get("passo") or i.get("id"): i for i in estado["checklist"]["itens"]}
        assert any(i.get("ok") or i.get("detectado") for i in itens.values()), itens
    finally:
        contexto.close()
