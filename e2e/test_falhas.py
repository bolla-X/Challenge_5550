"""Injeção de falhas (MISSÃO 4, Fase 5 item 4): o que a TELA diz quando algo some, e a recuperação.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). Cada falha tem uma mensagem clara na
interface (nunca uma tela muda ou um erro técnico) e uma recuperação provada, e o resto do sistema segue de pé.

Cobertas aqui, no navegador:
- a câmera de rede cai e volta ("Reconectando" / "Sem sinal" e depois "Ao vivo");
- a webcam ausente (câmera USB de índice 9): "Sem sinal"/"Reconectando", sem derrubar as outras câmeras;
- a sessão que expira no MEIO de uma ação: aviso de sessão expirada e volta à mesma tela depois do login;
- a página de status diz o que está no ar (OPC UA, MQTT, broker) e que a segunda opinião (LLM) está desligada.

Cobertas em outro nível, SEM duplicar aqui (referência em vez de teste):
- modelo ausente: tests/test_falhas_da_demo.py::test_modelo_ausente_nao_derruba_a_analise;
- banco travado/indisponível: tests/test_falhas_da_demo.py::test_banco_indisponivel_aparece_no_checklist;
- LLM fora do ar no resumo do relatório: tests/test_falhas_da_demo.py::test_llm_fora_do_ar_no_resumo_do_relatorio
  (e a degradação do analisador: tests/test_llm.py::test_provedor_indisponivel_degrada_para_none);
- webcam ausente na semeadura da demo: tests/test_falhas_da_demo.py::test_webcam_ausente_o_portal_toca_a_gravacao_do_portal;
- fonte morta, backoff e fonte de reserva: tests/test_camera_worker_falha_de_fonte.py.

Porta OPC UA ocupada e broker MQTT fora ficam `skip` neste arquivo (precisam de OUTRO servidor, custo alto):
ver os dois testes marcados, com a razão e onde estão cobertos.

Timeouts generosos para esta máquina lenta: login 60 s; câmera cair/voltar 90 s e 120 s; webcam ausente 120 s;
sessão expirada 30 s; página de status 60 s.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from conftest import entrar, esperar

NOMES_DAS_CAMERAS = ("Multidão", "Canteiro", "Rede", "Queda")


def _todas_rodando(sessao, servidor) -> dict[str, bool]:
    return {nome: bool(sessao.get(f"{servidor.base}/api/cameras/{servidor.cameras[nome]}/status", timeout=20).json().get("running"))
            for nome in NOMES_DAS_CAMERAS}


# ------------------------------------------------------------ câmera que cai e volta
def test_camera_cai_a_tela_diz_reconectando_e_volta(pagina, servidor):
    """A fonte de rede para de responder: a tela troca "Ao vivo" por "Reconectando"/"Sem sinal" e, quando a
    fonte volta, volta a "Ao vivo" sozinha. Movida de e2e/test_fluxos.py (sem duplicar)."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Configurar Rede").click(timeout=60_000)
    badge = pagina.locator(".feed-badge").first
    esperar(lambda: badge.get_attribute("data-estado") == "ao_vivo", 90, 0.5, msg="a fonte de rede nunca ficou ao vivo")

    servidor.fonte_rede.parar()
    try:
        def caiu():
            estado = badge.get_attribute("data-estado") or ""
            return estado in ("reconectando", "sem_sinal") and (estado, badge.inner_text())

        estado, texto = esperar(caiu, 90, 0.3, msg="a queda da fonte não apareceu na tela")
        assert re.search(r"Reconectando|Sem sinal", texto), (estado, texto)
    finally:
        servidor.fonte_rede.iniciar()
    esperar(lambda: badge.get_attribute("data-estado") == "ao_vivo", 120, 0.5, msg="a fonte voltou e a tela não")


# ------------------------------------------------------------ webcam ausente
def test_webcam_ausente_diz_sem_sinal_e_nao_derruba_as_outras(pagina, servidor):
    """Câmera USB de índice 9 (não existe): fica sem sinal/reconectando, com a mensagem na tela, e as 4 câmeras de
    fixture seguem rodando. A câmera de teste é removida no fim."""
    tecnico = servidor.sessao("technical")
    criada = tecnico.post(f"{servidor.base}/api/cameras", json={"name": "Webcam ausente", "source_type": "USB", "source": "9",
                                                                  "fps": 12, "width": 960, "height": 540}, timeout=20)
    assert criada.status_code in (200, 201), criada.text
    cid = criada.json()["id"]
    try:
        assert tecnico.post(f"{servidor.base}/api/cameras/{cid}/start", timeout=60).status_code == 200

        def sem_imagem():
            estado = tecnico.get(f"{servidor.base}/api/cameras/{cid}/status", timeout=20).json()
            return estado.get("running") and (estado.get("video") or {}).get("state") in ("reconnecting", "unavailable") and estado

        estado = esperar(sem_imagem, 120, 2, msg="a webcam ausente não foi dada como sem sinal/reconectando")
        assert estado["video"]["modo"] == "reconectando", estado["video"]

        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Configurar Webcam ausente").click(timeout=60_000)
        badge = pagina.locator(".feed-badge").first
        esperar(lambda: badge.get_attribute("data-estado") in ("sem_sinal", "reconectando"), 90, 0.5,
                msg="a tela não disse que a webcam está sem sinal")
        assert re.search(r"Sem sinal|Reconectando", badge.inner_text()), badge.inner_text()

        # Nada mais caiu: as outras câmeras seguem rodando e a sessão continua boa.
        assert _todas_rodando(tecnico, servidor) == dict.fromkeys(NOMES_DAS_CAMERAS, True)
        assert pagina.request.get(f"{servidor.base}/api/auth/me").json()["user"] is not None
    finally:
        tecnico.post(f"{servidor.base}/api/cameras/{cid}/stop", timeout=60)
        tecnico.delete(f"{servidor.base}/api/cameras/{cid}", timeout=20)
    nomes = {c["name"] for c in tecnico.get(f"{servidor.base}/api/cameras", timeout=20).json()["items"]}
    assert "Webcam ausente" not in nomes, nomes
    assert _todas_rodando(tecnico, servidor) == dict.fromkeys(NOMES_DAS_CAMERAS, True)


# ------------------------------------------------------------ sessão expirada no meio de uma ação
def test_sessao_expirada_no_meio_de_uma_acao_avisa_e_volta_depois_do_login(pagina, servidor):
    """O cookie some (sessão expirada por fora) e a pessoa aciona "Buscar": a resposta 401 leva ao login com o aviso
    "Sua sessão expirou" e, depois de entrar, ela volta para a mesma tela e a ação funciona.

    (A tela da evacuação que expira sozinha, sem ação, é test_missao4.py::test_sessao_expirada_volta_para_onde_estava.)"""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/busca")
    pagina.locator("[data-testid=busca-trilhas]").wait_for(timeout=60_000)
    pagina.get_by_label("Câmera", exact=True).wait_for(timeout=60_000)

    pagina.context.clear_cookies()
    try:
        pagina.locator("[data-testid=busca-filtrar]").click(timeout=3_000)
    except PlaywrightTimeout:
        pass  # uma chamada de fundo já levou a tela ao login: o aviso abaixo é o mesmo
    aviso = pagina.locator("[data-testid=sessao-expirada]")
    aviso.wait_for(timeout=30_000)
    assert "sessão expirou" in aviso.inner_text()

    pagina.get_by_label("E-mail").fill(servidor.emails["technical"])
    pagina.get_by_label("Senha").fill(servidor.senhas["technical"])
    pagina.get_by_role("button", name="Entrar").click()
    pagina.wait_for_url("**/busca", timeout=60_000)
    pagina.locator("[data-testid=busca-trilhas]").wait_for(timeout=60_000)
    pagina.get_by_label("Câmera", exact=True).wait_for(timeout=60_000)
    pagina.locator("[data-testid=busca-filtrar]").click()
    pagina.locator("[data-testid=busca-estado][data-estado=pronto]").wait_for(timeout=60_000)


# ------------------------------------------------------------ status: o que está no ar e o LLM desligado
def test_status_diz_o_que_esta_no_ar_e_que_o_llm_esta_desligado(pagina, servidor):
    """A página de status mostra OPC UA, MQTT e broker no ar (com o endereço) e a segunda opinião (LLM) desligada
    com a frase de que o resto funciona; o relatório do turno, que não depende de LLM, responde.

    O LLM está desligado no E2E (LLM_ENABLED=false); o resumo falhando com o provedor fora do ar está em
    tests/test_falhas_da_demo.py::test_llm_fora_do_ar_no_resumo_do_relatorio."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/status")
    pagina.locator("[data-testid=pagina-status]").wait_for(timeout=60_000)
    for chave in ("opcua", "mqtt", "broker"):
        pagina.locator(f"[data-testid=status-{chave}][data-estado=ok]").wait_for(timeout=60_000)
    assert str(servidor.porta_opcua) in pagina.locator("[data-testid=status-opcua]").inner_text()
    llm = pagina.locator("[data-testid=status-llm][data-estado=desligado]")
    llm.wait_for(timeout=30_000)
    assert "O resto do sistema funciona normalmente" in llm.inner_text(), llm.inner_text()
    assert pagina.request.get(f"{servidor.base}/api/relatorio/turno").status == 200


# ------------------------------------------------------------ porta OPC UA ocupada e broker MQTT fora
@pytest.mark.skip(reason="Precisa de um SEGUNDO servidor (a porta OPC UA tem de estar ocupada ANTES de ele subir): custo alto. "
                         "Coberto no nível de integração: tests/test_integracao_industrial.py::"
                         "test_gerente_porta_opcua_ocupada_vira_status_falhou_sem_excecao (status `falhou` com mensagem, sem exceção) e "
                         "test_gerente_porta_invalida_vira_falhou_com_mensagem; o cartão da página de status mostra o motivo "
                         "(`status-opcua`, linha Motivo) e o que está no ar é provado em "
                         "test_status_diz_o_que_esta_no_ar_e_que_o_llm_esta_desligado.")
def test_porta_opcua_ocupada_aparece_como_falhou_com_mensagem():
    """/api/integracao/estado mostra `falhou` + `erro` quando a porta já estava ocupada (ver o motivo do skip)."""


@pytest.mark.skip(reason="Precisa de um SEGUNDO servidor (broker MQTT inalcançável desde o boot) ou derrubar o broker embutido do servidor "
                         "compartilhado, o que quebraria os outros testes: custo alto. Coberto no nível de integração: "
                         "tests/test_integracao_industrial.py::test_gerente_broker_mqtt_fora_vira_falhou_e_nao_lanca_ao_publicar, "
                         "test_mqtt_com_broker_fora_nao_lanca_e_status_indica_desconectado, "
                         "test_mqtt_reconecta_sozinho_e_entrega_o_estado_enfileirado_quando_o_broker_volta (recuperação) e "
                         "test_broker_embutido_em_porta_ocupada_falha_com_mensagem_legivel.")
def test_broker_mqtt_fora_aparece_como_falhou_e_recupera():
    """/api/integracao/estado mostra `falhou` com o motivo e volta a `no_ar` quando o broker volta (ver o motivo do skip)."""
