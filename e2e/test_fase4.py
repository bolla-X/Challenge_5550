"""E2E da Fase 4 da MISSÃO 4: escalonamento, intervenções com ROI, relatório mensal e API documentada.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). O servidor do E2E sobe com os prazos de
escalonamento CURTOS (`ESCALONAR_SUPERVISOR_S=20` e `ESCALONAR_TV_S=40`, em conftest.py) para o teste não esperar os
60 s e 180 s de produção.

- M7 escalonamento: alerta crítico sem reconhecimento gera, uma vez por nível, a linha `alerta_escalonado` na linha do
  tempo (nível 1 ao supervisor, nível 2 à TV e à torre) e a câmera fica `escalonado` em `/api/integracao/estado` (e a
  torre da tela pisca: `data-escalonado`); reconhecer encerra o escalonamento;
- M8 intervenções: criadas pela API, abertas em `/intervencoes`, com o aviso "Correlação não é causa" e o ROI só com as
  premissas digitadas;
- M10 relatório mensal (CIPA): abre e não traz "Pessoa N" nem e-mail;
- M11 `/api/docs` e `/api/openapi.json`: técnico 200, operador 403, sem login 401.

Timeouts generosos para esta máquina lenta: login 60 s; escalonar até 300 s (crítico de 40 s de idade mais o tique de
1 s e a carga da máquina); telas 30-60 s.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from conftest import entrar, esperar

# Rótulo de rastreio: "Pessoa 3", "Pessoa A7"... O nome de uma regra continua em minúscula
# ("Pessoa em área de risco", "Pessoa imóvel na área de risco") e não é rótulo de ninguém.
ROTULO_DE_RASTREIO = re.compile(r"\bPessoa\s+(?![a-záàâãéêíóôõúç])\S")

TITULO_DA_INTERVENCAO = "E2E: capacete obrigatório no portão da Multidão"


# --------------------------------------------------------------- M7 escalonamento
def _criticos_sem_reconhecer(sessao, servidor) -> dict[int, int]:
    """Alertas críticos ATIVOS que ninguém reconheceu: id do alerta -> id da câmera."""
    itens = sessao.get(f"{servidor.base}/alerts", params={"status": "active", "severity": "critical", "limit": 500},
                       timeout=30).json()["items"]
    return {a["id"]: a["camera_id"] for a in itens if not a.get("acknowledged")}


def _cameras_escalonadas(sessao, servidor) -> set[int]:
    planta = sessao.get(f"{servidor.base}/api/integracao/estado", timeout=20).json()["planta"]
    return {c["id"] for c in planta["cameras"] if c.get("escalonado")}


def test_alerta_critico_sem_reconhecimento_escala_ao_supervisor_e_a_tv_e_reconhecer_encerra(pagina, servidor):
    assert (servidor.env["ESCALONAR_SUPERVISOR_S"], servidor.env["ESCALONAR_TV_S"]) == ("20", "40"), \
        "o servidor do E2E tem de subir com os prazos curtos de escalonamento (conftest.py)"
    supervisor = servidor.sessao("supervisor")

    def escalou():
        criticos = _criticos_sem_reconhecer(supervisor, servidor)
        if not criticos:
            return False
        eventos = supervisor.get(f"{servidor.base}/events", params={"event_type": "alerta_escalonado", "limit": 300},
                                 timeout=30).json()["items"]
        por_alerta: dict[int, dict[int, dict]] = {}
        for evento in eventos:
            meta = evento.get("metadata") or {}
            if meta.get("alerta_id") in criticos:
                por_alerta.setdefault(meta["alerta_id"], {})[meta.get("nivel")] = evento
        for alerta_id, niveis in por_alerta.items():
            # O mesmo alerta que ainda está ativo e sem reconhecimento já subiu aos dois níveis e a câmera dele está escalonada.
            if {1, 2} <= set(niveis) and criticos[alerta_id] in _cameras_escalonadas(supervisor, servidor):
                return {"alerta_id": alerta_id, "camera_id": criticos[alerta_id], "niveis": niveis}
        return False

    achado = esperar(escalou, 300, 2, msg="nenhum alerta crítico sem reconhecimento chegou aos dois níveis de escalonamento")
    camera_id = achado["camera_id"]
    nivel1, nivel2 = achado["niveis"][1], achado["niveis"][2]
    assert (nivel1["severity"], nivel2["severity"]) == ("high", "critical"), (nivel1, nivel2)
    assert (nivel1["metadata"]["papel"], nivel2["metadata"]["papel"]) == ("supervisor", "tv_torre")
    assert nivel1["camera_id"] == nivel2["camera_id"] == camera_id
    assert "sem reconhecimento" in nivel1["message"] and "sem reconhecimento" in nivel2["message"]
    assert nivel1["metadata"]["segundos_sem_reconhecer"] >= 20 and nivel2["metadata"]["segundos_sem_reconhecer"] >= 40, achado["niveis"]
    if nivel1["metadata"]["origem_do_prazo"] == "configuracao":  # alerta sem prazo próprio de regra: valem os do servidor
        assert (nivel1["metadata"]["prazo_s"], nivel2["metadata"]["prazo_s"]) == (20, 40), achado["niveis"]

    # A torre de luz na tela pisca para a supervisão.
    entrar(pagina, servidor, "supervisor")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/torre")
    pagina.locator("[data-testid=torre][data-escalonado='1']").wait_for(timeout=60_000)

    # Reconhecer encerra: a câmera deixa de ficar escalonada.
    resposta = supervisor.post(f"{servidor.base}/alerts/acknowledge-all", params={"camera_id": camera_id}, json={"note": "e2e"}, timeout=20)
    assert resposta.status_code == 200 and resposta.json()["acknowledged"] >= 1, resposta.text
    esperar(lambda: camera_id not in _cameras_escalonadas(supervisor, servidor), 60, 1,
            msg="a câmera continuou escalonada depois de reconhecer os alertas")


# --------------------------------------------------------------- M8 intervenções e ROI
def test_intervencao_antes_e_depois_com_aviso_de_correlacao_e_roi_das_premissas(pagina, servidor):
    supervisor = servidor.sessao("supervisor")
    tecnico = servidor.sessao("technical")
    multidao = servidor.cameras["Multidão"]
    corpo = {"titulo": TITULO_DA_INTERVENCAO, "descricao": "Placa e checagem de capacete na entrada.",
             "data_da_intervencao": (date.today() - timedelta(days=3)).isoformat(), "camera_id": multidao}
    # Só o supervisor registra; o técnico lê e calcula; o operador não vê a tela.
    assert tecnico.post(f"{servidor.base}/api/intervencoes", json=corpo, timeout=20).status_code == 403
    assert servidor.sessao("operator").get(f"{servidor.base}/api/intervencoes", timeout=20).status_code == 403
    criada = supervisor.post(f"{servidor.base}/api/intervencoes", json=corpo, timeout=20)
    assert criada.status_code == 201, criada.text
    ident = criada.json()["intervencao"]["id"]
    try:
        comparacao = tecnico.get(f"{servidor.base}/api/intervencoes/{ident}/comparacao", params={"janela_dias": 7}, timeout=30)
        assert comparacao.status_code == 200, comparacao.text
        assert "Correlação não é causa" in comparacao.json()["aviso"]
        roi = tecnico.post(f"{servidor.base}/api/intervencoes/{ident}/roi", timeout=20,
                           json={"custo_da_intervencao": 1000, "incidentes_evitados": 10, "custo_medio_por_incidente": 500,
                                 "periodo_dias": 30}).json()
        assert roi["resultado"]["economia"] == 5000 and roi["resultado"]["ganho_liquido"] == 4000, roi

        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        pagina.goto(servidor.base + "/intervencoes")
        pagina.locator("[data-testid=intervencoes]").wait_for(timeout=60_000)
        pagina.get_by_role("button", name=re.compile(re.escape(TITULO_DA_INTERVENCAO))).click(timeout=30_000)

        # A comparação antes/depois sempre vem com o aviso de que correlação não é causa.
        pagina.locator("[data-testid=intervencao-comparacao]").wait_for(timeout=30_000)
        assert "Correlação não é causa" in pagina.locator("[data-testid=intervencao-aviso]").inner_text()

        # ROI: sem premissas pede os números; com as premissas calcula e mostra a fórmula e o aviso de estimativa.
        roi_tela = pagina.locator("[data-testid=intervencao-roi]")
        assert "Digite os seus números" in roi_tela.inner_text()
        roi_tela.get_by_role("button", name="Calcular").click()
        roi_tela.get_by_role("alert").wait_for(timeout=15_000)
        assert "Preencha os números obrigatórios" in roi_tela.get_by_role("alert").inner_text()
        roi_tela.get_by_label("Custo da intervenção (R$)", exact=True).fill("1000")
        roi_tela.get_by_label("Incidentes evitados no período", exact=True).fill("10")
        roi_tela.get_by_label("Período dos incidentes evitados (dias)", exact=True).fill("30")
        roi_tela.get_by_label("Custo médio estimado de um incidente (R$)", exact=True).fill("500")
        roi_tela.get_by_role("button", name="Calcular").click()
        resultado = pagina.locator("[data-testid=roi-resultado]")
        resultado.wait_for(timeout=15_000)
        texto = resultado.inner_text()
        assert "Estimativa com as suas premissas" in texto, texto
        assert re.search(r"R\$\s*5\.000,00", texto) and re.search(r"R\$\s*4\.000,00", texto), texto  # economia e ganho líquido
        assert "Ganho líquido" in resultado.get_by_label("Fórmula usada").inner_text()
    finally:
        supervisor.delete(f"{servidor.base}/api/intervencoes/{ident}", timeout=20)


# --------------------------------------------------------------- M10 relatório mensal
def test_relatorio_mensal_abre_sem_pessoa_nem_email(pagina, servidor):
    supervisor = servidor.sessao("supervisor")
    # O que a pessoa lê: nenhum rótulo de rastreio ("Pessoa N") nem e-mail. O `<style>` fica de fora (tem `@page` e `@font-face`).
    bruto = supervisor.get(f"{servidor.base}/relatorio/mensal", timeout=60)
    assert bruto.status_code == 200 and bruto.headers["Content-Type"].startswith("text/html"), bruto.status_code
    sem_estilo = re.sub(r"<style\b.*?</style>", "", bruto.text, flags=re.DOTALL | re.IGNORECASE)
    assert not ROTULO_DE_RASTREIO.search(sem_estilo), "o relatório mensal não pode trazer rótulo de rastreio"
    assert "@" not in sem_estilo, "o relatório mensal não pode trazer e-mail nem menção"

    entrar(pagina, servidor, "supervisor")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    pagina.goto(servidor.base + "/relatorio/mensal")
    pagina.get_by_role("heading", name="Relatório mensal para a CIPA").wait_for(timeout=60_000)
    for secao in ("Alertas", "Incidentes", "Fonte de cada número"):
        pagina.get_by_role("heading", name=secao, exact=True).wait_for(timeout=15_000)
    visivel = pagina.locator("body").inner_text()
    assert not ROTULO_DE_RASTREIO.search(visivel) and "@" not in visivel, visivel[:500]
    # Mês inválido: mensagem em português, não uma página quebrada.
    invalido = supervisor.get(f"{servidor.base}/api/relatorio/mensal", params={"mes": "2026-13"}, timeout=20)
    assert invalido.status_code == 400 and "AAAA-MM" in invalido.json()["error"], invalido.text


# --------------------------------------------------------------- M11 API documentada
def test_api_docs_e_openapi_so_para_tecnico_ou_acima(servidor):
    import requests

    docs, openapi = f"{servidor.base}/api/docs", f"{servidor.base}/api/openapi.json"
    for url in (docs, openapi):
        assert requests.get(url, timeout=20).status_code == 401, f"{url} aberta sem login"
        assert servidor.sessao("operator").get(url, timeout=20).status_code == 403, f"{url} aberta ao operador"
    for papel in ("technical", "supervisor"):
        sessao = servidor.sessao(papel)
        pagina_docs = sessao.get(docs, timeout=30)
        assert pagina_docs.status_code == 200 and pagina_docs.headers["Content-Type"].startswith("text/html"), papel
        assert "curl" in pagina_docs.text.lower(), "a página da API traz exemplos de curl"
        documento = sessao.get(openapi, timeout=30)
        assert documento.status_code == 200, papel
        corpo = documento.json()
        assert corpo["openapi"].startswith("3.1"), corpo["openapi"]
        assert "/alerts" in corpo["paths"] and "/api/incidentes" in corpo["paths"], list(corpo["paths"])[:10]
