"""E2E da entrega de Engenharia de Software (Sprint 4): cada fluxo principal, no modo demonstração.

    python -m pytest e2e/test_es_sprint4.py -q

Sobe `run.py --demo` de um checkout (o deste repositório, ou outro: `VISIONEPI_RAIZ`,
com o Python em `VISIONEPI_PYTHON`) — é o mesmo teste do "avaliador" no clone limpo
(docs/specs/es-sprint4.md, F2.2). Sem câmera IP, sem webcam (`DEMO_WEBCAM=0`), sem
`GEMINI_API_KEY`. As senhas da demo são lidas do terminal e nunca vão para o log.

Fluxos (critério F1.6): dashboard, monitoramento em tempo real, alertas, segunda
opinião em modo demonstração, colaboradores com histórico de EPIs, catálogo com CA,
entregas (com o bloqueio de CA vencido), ocorrências, relatório e exportação, tema escuro.

Não usa a fixture `servidor` do conftest (aquela sobe outro servidor, com outras câmeras).
"""

from __future__ import annotations

import csv
import io
import os
import re
import time
from pathlib import Path

import pytest
from fumaca_demo import DemoEm

from conftest import RAIZ, entrar

CAPTURAS = RAIZ / "bench" / "runtime" / "e2e-es-sprint4"


@pytest.fixture(scope="module")
def demo():
    raiz = Path(os.environ.get("VISIONEPI_RAIZ") or RAIZ).resolve()
    padrao = raiz / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    instancia = DemoEm(raiz, Path(os.environ.get("VISIONEPI_PYTHON") or padrao))
    try:
        instancia.subir()
        yield instancia
    finally:
        instancia.parar()


@pytest.fixture(scope="module")
def sessao(demo):
    return demo.sessao("supervisor")


@pytest.fixture()
def tela(navegador, demo, request):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
    pagina = contexto.new_page()
    erros: list[str] = []
    pagina.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pagina.erros_console = erros
    entrar(pagina, demo, "supervisor")
    pagina.get_by_role("button", name=re.compile(r"Câmeras|Início")).first.wait_for(timeout=60_000)
    yield pagina
    # Diagnóstico: a última tela de cada teste fica em bench/runtime/e2e-es-sprint4/.
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    try:
        pagina.screenshot(path=str(CAPTURAS / f"{request.node.name}.png"))
    finally:
        contexto.close()


def _camera(sessao, demo, nome: str) -> int:
    corpo = sessao.get(demo.base + "/api/cameras", timeout=10).json()
    cameras = corpo if isinstance(corpo, list) else corpo.get("items") or corpo.get("cameras") or []
    return {c["name"]: c["id"] for c in cameras}[nome]


def _gestao(tela, demo, aba: str):
    tela.goto(demo.base + "/gestao")
    tela.locator("[data-testid=gestao]").wait_for(timeout=30_000)
    tela.locator(f"[data-testid=gestao-aba-{aba}]").click()


# ---------------------------------------------------------------- dashboard ---
def test_dashboard_inicio_mostra_resumo_da_gestao(tela, demo, sessao):
    resumo = sessao.get(demo.base + "/api/gestao/resumo", timeout=10).json()
    assert resumo["colaboradores_ativos"] >= 20 and resumo["simulados"] is True
    assert resumo["cas_vencidos"] >= 1
    # Visão geral (painel por setor) a partir da grade.
    tela.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
    tela.get_by_role("button", name="Visão geral").click(timeout=30_000)
    tela.get_by_text("Por setor, nunca por pessoa").first.wait_for(timeout=30_000)


# ------------------------------------------------------ monitoramento ao vivo ---
def test_monitoramento_em_tempo_real_video_chega_ao_canvas(tela, demo):
    tela.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
    tela.get_by_role("button", name=re.compile("Configurar Pátio")).click(timeout=30_000)
    video = tela.locator("canvas.live-video").first
    video.wait_for(timeout=30_000)
    fim = time.monotonic() + 90
    quadros = 0
    while time.monotonic() < fim and quadros < 10:
        quadros = int(video.get_attribute("data-frames") or 0)
        time.sleep(0.5)
    assert quadros >= 10, f"{quadros} quadros"


# --------------------------------------------------------------------- alertas ---
def test_alertas_nascem_da_deteccao_e_aparecem_como_incidente(tela, demo, sessao):
    cid = _camera(sessao, demo, "Pátio")
    fim = time.monotonic() + 240
    ativos: list = []
    while time.monotonic() < fim and not ativos:
        ativos = sessao.get(f"{demo.base}/api/cameras/{cid}/status", timeout=20).json().get("active_alerts") or []
        time.sleep(2)
    assert ativos, "nenhum alerta ativo no Pátio em 240 s"
    tela.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
    tela.get_by_role("button", name=re.compile("Configurar Pátio")).click(timeout=30_000)
    tela.locator("[role=tablist]").first.wait_for(timeout=30_000)
    aba = tela.get_by_role("tab", name="Alertas")
    if aba.count():
        aba.click()
    else:
        tela.locator(".tabs-more > button").click()
        tela.get_by_role("menuitem", name="Alertas").click()
    tela.locator("[data-testid=incidente]").first.wait_for(timeout=120_000)


def test_segunda_opiniao_sem_chave_e_rotulada_modo_demonstracao(demo, sessao):
    cid = _camera(sessao, demo, "Pátio")
    fim = time.monotonic() + 240
    llm: dict = {}
    while time.monotonic() < fim:
        llm = sessao.get(f"{demo.base}/api/cameras/{cid}/status", timeout=20).json().get("llm") or {}
        if llm.get("ultima"):
            break
        time.sleep(2)
    assert llm.get("habilitado") is True and llm.get("modo") == "demonstracao", llm
    assert llm.get("ultima") and "Modo demonstração" in llm["ultima"]["justificativa"], llm
    status = sessao.get(demo.base + "/api/status", timeout=30).json()
    assert "Modo demonstração" in status["componentes"]["llm"]["resumo"]


# ------------------------------------------------- colaboradores e histórico ---
def test_colaborador_tem_historico_de_epis(tela, demo):
    _gestao(tela, demo, "colaboradores")
    primeiro = tela.locator("[data-testid^=gestao-colaborador-]").first
    primeiro.wait_for(timeout=30_000)
    primeiro.click()
    historico = tela.locator("[data-testid=gestao-historico]")
    historico.wait_for(timeout=30_000)
    texto = historico.inner_text()
    assert re.search(r"\d{2}/\d{2}/\d{4}", texto), texto[:300]
    assert re.search(r"(?i)vigente|troca vencida|devolvido", texto), texto[:300]
    assert not tela.erros_console, tela.erros_console


def test_catalogo_mostra_ca_e_situacao_da_validade(tela, demo):
    _gestao(tela, demo, "catalogo")
    corpo = tela.locator("[data-testid=gestao]")
    tela.locator("[data-testid=gestao-tabela-epis]").get_by_text(re.compile(r"Vencido h")).first.wait_for(timeout=30_000)
    assert re.search(r"\b9\d{5}\b", corpo.inner_text()), "nenhum CA (faixa fictícia 9xxxxx) na tela"


# -------------------------------------------------------------------- entregas ---
def test_entrega_com_ca_vencido_e_bloqueada_e_valida_e_registrada(demo, sessao):
    base = demo.base
    epis = sessao.get(base + "/api/gestao/epis", timeout=10).json()["items"]
    vencido = next(e for e in epis if e["situacao_ca"] == "vencido")
    valido = next(e for e in epis if e["situacao_ca"] == "valido")
    colaborador = sessao.get(base + "/api/gestao/colaboradores", timeout=10).json()["items"][0]
    hoje = time.strftime("%Y-%m-%d")
    corpo = {"colaborador_id": colaborador["id"], "quantidade": 1, "entregue_em": hoje, "motivo": "substituicao"}

    negada = sessao.post(base + "/api/gestao/entregas", json=corpo | {"epi_id": vencido["id"]}, timeout=10)
    assert negada.status_code == 409 and negada.json()["code"] == "ca_vencido"

    feita = sessao.post(base + "/api/gestao/entregas", json=corpo | {"epi_id": valido["id"]}, timeout=10)
    assert feita.status_code == 201, feita.text
    detalhe = sessao.get(f"{base}/api/gestao/colaboradores/{colaborador['id']}", timeout=10).json()
    assert detalhe["entregas"][0]["id"] == feita.json()["entrega"]["id"]  # histórico: mais recente primeiro


def test_formulario_de_entrega_explica_o_bloqueio_de_ca_vencido(tela, demo, sessao):
    epis = sessao.get(demo.base + "/api/gestao/epis", timeout=10).json()["items"]
    vencido = next(e for e in epis if e["situacao_ca"] == "vencido")
    _gestao(tela, demo, "entregas")
    tela.locator("[data-testid=gestao-nova-entrega]").click()
    form = tela.locator("[data-testid=gestao-form-entrega]")
    form.wait_for(timeout=10_000)
    form.locator("[data-testid=gestao-entrega-colaborador]").select_option(index=1)
    form.locator("[data-testid=gestao-entrega-epi]").select_option(value=str(vencido["id"]))
    form.get_by_role("button", name=re.compile("Registrar")).last.click()
    form.get_by_role("alert").filter(has_text=re.compile("CA")).first.wait_for(timeout=10_000)


# ----------------------------------------------------------------- ocorrências ---
def test_ocorrencia_registrada_aparece_na_lista(tela, demo, sessao):
    descricao = f"E2E ES Sprint 4 — piso escorregadio na doca {int(time.time())}"
    _gestao(tela, demo, "ocorrencias")
    tela.locator("[data-testid=gestao-nova-ocorrencia]").click()
    form = tela.locator("[data-testid=gestao-form-ocorrencia]")
    form.wait_for(timeout=10_000)
    form.get_by_label(re.compile("Tipo")).select_option("condicao_insegura")
    form.get_by_label(re.compile("Gravidade")).select_option("media")
    form.get_by_label(re.compile("Setor")).fill("Expedição")
    form.get_by_label(re.compile("Descrição")).fill(descricao)
    form.get_by_role("button", name=re.compile("Registrar")).last.click()
    # Na TABELA, não na página: o texto digitado na <textarea> também casa com get_by_text antes de a ocorrência ser gravada.
    tela.locator("[data-testid=gestao-tabela-ocorrencias]").get_by_text(descricao).first.wait_for(timeout=15_000)
    itens = sessao.get(demo.base + "/api/gestao/ocorrencias", timeout=10).json()["items"]
    assert any(o["descricao"] == descricao and o["status"] == "aberta" for o in itens)


# --------------------------------------------------------- relatório e exportação ---
def test_exportacao_csv_e_relatorio_mensal(tela, demo):
    _gestao(tela, demo, "relatorios")
    with tela.expect_download() as baixado:
        tela.locator("[data-testid=gestao-exportar-entregas]").click()
    arquivo = baixado.value
    assert re.match(r"visionepi-entregas-\d{4}-\d{2}-\d{2}\.csv", arquivo.suggested_filename)
    conteudo = Path(arquivo.path()).read_bytes().decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(conteudo), delimiter=";"))
    assert len(linhas) > 10, linhas[:3]
    tela.goto(demo.base + "/relatorio/mensal")
    tela.wait_for_load_state("load")
    assert re.search(r"(?i)relat[óo]rio", tela.content())


# ------------------------------------------------- revisão de UX/UI/CX: provas ---
TABELA_DA_ABA = {"catalogo": "gestao-tabela-epis", "entregas": "gestao-tabela-entregas", "ocorrencias": "gestao-tabela-ocorrencias",
                 "colaboradores": "gestao-tabela-colaboradores"}


@pytest.mark.parametrize("aba", sorted(TABELA_DA_ABA))
def test_gestao_no_celular_nao_estoura_a_largura(navegador, demo, aba):
    """390x844: a tabela rola dentro do cartão; a página não ganha rolagem horizontal."""
    contexto = navegador.new_context(viewport={"width": 390, "height": 844})
    pagina = contexto.new_page()
    try:
        entrar(pagina, demo, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"Câmeras|Início")).first.wait_for(timeout=60_000)
        pagina.goto(f"{demo.base}/gestao?aba={aba}")
        pagina.locator(f"[data-testid={TABELA_DA_ABA[aba]}]").wait_for(timeout=30_000)  # sem a tabela, a medida seria de uma tela vazia
        largura = pagina.evaluate("document.documentElement.scrollWidth")
        assert largura <= 390, f"{aba}: scrollWidth {largura} > 390"
    finally:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURAS / f"test_gestao_no_celular_{aba}.png"))
        contexto.close()


def test_tecnico_nao_ve_o_que_so_o_supervisor_faz(navegador, demo):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    pagina = contexto.new_page()
    try:
        entrar(pagina, demo, "technical")
        pagina.get_by_label("E-mail").wait_for(state="hidden", timeout=60_000)  # saiu do login (o técnico não tem o botão "Câmeras")
        pagina.goto(demo.base + "/gestao")
        pagina.locator("[data-testid=gestao]").wait_for(timeout=30_000)
        pagina.locator("[data-testid=gestao-tabela-colaboradores]").wait_for(timeout=30_000)
        assert pagina.locator("[data-testid=gestao-novo-colaborador]").count() == 0
        pagina.locator("[data-testid=gestao-aba-catalogo]").click()
        pagina.locator("[data-testid=gestao-tabela-epis]").wait_for(timeout=30_000)
        assert pagina.locator("[data-testid=gestao-novo-epi]").count() == 0
    finally:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURAS / "test_tecnico_nao_ve_o_que_so_o_supervisor_faz.png"))
        contexto.close()


def test_operador_em_gestao_ve_acesso_negado(navegador, demo):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    pagina = contexto.new_page()
    try:
        entrar(pagina, demo, "operator")
        pagina.get_by_label("E-mail").wait_for(state="hidden", timeout=60_000)  # saiu do login
        pagina.goto(demo.base + "/gestao")
        pagina.get_by_role("alert").filter(has_text=re.compile("Esta tela é para")).wait_for(timeout=30_000)
        assert pagina.locator("[data-testid=gestao]").count() == 0
    finally:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURAS / "test_operador_em_gestao_ve_acesso_negado.png"))
        contexto.close()


def test_supervisor_ve_o_aviso_de_dados_simulados(tela, demo):
    tela.goto(demo.base + "/gestao")
    tela.locator("[data-testid=gestao-simulados]").wait_for(timeout=30_000)
    tela.get_by_text("Dados simulados: nomes, fabricantes e CAs fictícios").wait_for(timeout=10_000)


def test_formulario_de_entrega_avisa_antes_de_enviar_e_cuida_do_foco(tela, demo, sessao):
    epis = sessao.get(demo.base + "/api/gestao/epis", timeout=10).json()["items"]
    vencido = next(e for e in epis if e["situacao_ca"] == "vencido")
    _gestao(tela, demo, "entregas")
    abrir = tela.locator("[data-testid=gestao-nova-entrega]")
    abrir.click()
    form = tela.locator("[data-testid=gestao-form-entrega]")
    form.wait_for(timeout=10_000)
    # Abrir move o foco para dentro do formulário.
    tela.wait_for_function(
        "() => document.querySelector('[data-testid=gestao-form-entrega]')?.contains(document.activeElement) === true",
        timeout=10_000,
    )
    # O aviso aparece ao ESCOLHER o EPI de CA vencido: nenhum envio aconteceu.
    pedidos: list[str] = []
    tela.on("request", lambda r: pedidos.append(r.method) if r.url.endswith("/api/gestao/entregas") and r.method == "POST" else None)
    form.locator("[data-testid=gestao-entrega-epi]").select_option(value=str(vencido["id"]))
    form.get_by_role("alert").filter(has_text="venceu em").first.wait_for(timeout=10_000)
    assert pedidos == []
    # Cancelar devolve o foco ao botão que abriu o formulário.
    form.get_by_role("button", name="Cancelar").click()
    form.wait_for(state="detached", timeout=10_000)
    tela.wait_for_function(
        "() => document.activeElement?.getAttribute('data-testid') === 'gestao-nova-entrega'", timeout=10_000
    )


def test_segunda_opiniao_na_tela_de_foco_mostra_o_modo_demonstracao(tela, demo, sessao):
    cid = _camera(sessao, demo, "Pátio")
    fim = time.monotonic() + 240
    llm: dict = {}
    while time.monotonic() < fim and not llm.get("ultima"):  # a resposta fixa só existe depois do 1º alerta
        llm = sessao.get(f"{demo.base}/api/cameras/{cid}/status", timeout=20).json().get("llm") or {}
        time.sleep(2)
    assert llm.get("ultima"), "nenhuma resposta fixa do LLM em 240 s"
    tela.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
    tela.get_by_role("button", name=re.compile("Configurar Pátio")).click(timeout=30_000)
    tela.locator("[role=tablist]").first.wait_for(timeout=30_000)
    aba = tela.get_by_role("tab", name="Segunda opinião")
    if aba.count():
        aba.click()
    else:
        tela.locator(".tabs-more > button").click()
        tela.get_by_role("menuitem", name="Segunda opinião").click()
    tela.locator("[data-testid=llm-modo-demonstracao]").wait_for(timeout=30_000)
    tela.locator("[data-testid=llm-exemplo-fixo]").wait_for(timeout=30_000)


def test_pagina_status_rotula_o_llm_como_demonstracao(tela, demo):
    tela.goto(demo.base + "/status")
    cartao = tela.locator("[data-testid=status-llm]")
    cartao.wait_for(timeout=60_000)
    cartao.get_by_text("Demonstração", exact=True).wait_for(timeout=10_000)
    assert cartao.get_by_text("Ligada", exact=True).count() == 0


# ------------------------------------------------------------- API: contrato de erro ---
def test_api_ocorrencia_com_colaborador_e_alerta_e_proibida(demo, sessao):
    colaborador = sessao.get(demo.base + "/api/gestao/colaboradores", timeout=10).json()["items"][0]
    corpo = {"tipo": "condicao_insegura", "gravidade": "media", "setor": "Expedição", "descricao": "vínculo proibido",
             "colaborador_id": colaborador["id"], "alerta_id": 1}
    r = sessao.post(demo.base + "/api/gestao/ocorrencias", json=corpo, timeout=10)
    assert r.status_code == 400 and r.json()["code"] == "vinculo_proibido", r.text


def test_api_entrega_com_data_no_futuro_e_recusada(demo, sessao):
    epi = next(e for e in sessao.get(demo.base + "/api/gestao/epis", timeout=10).json()["items"] if e["situacao_ca"] == "valido")
    colaborador = sessao.get(demo.base + "/api/gestao/colaboradores", timeout=10).json()["items"][0]
    futuro = time.strftime("%Y-%m-%d", time.localtime(time.time() + 30 * 86400))
    r = sessao.post(demo.base + "/api/gestao/entregas", timeout=10, json={
        "colaborador_id": colaborador["id"], "epi_id": epi["id"], "quantidade": 1, "entregue_em": futuro, "motivo": "substituicao"})
    assert r.status_code == 400 and r.json()["code"] == "data_invalida", r.text


def test_api_listagem_de_entregas_informa_se_foi_truncada(demo, sessao):
    corpo = sessao.get(demo.base + "/api/gestao/entregas", timeout=10).json()
    assert isinstance(corpo.get("truncado"), bool), list(corpo)
    assert corpo["count"] == len(corpo["items"])


def test_api_csv_de_entregas_tem_bom_e_separador_ponto_e_virgula(demo, sessao):
    r = sessao.get(demo.base + "/api/gestao/exportar/entregas.csv", timeout=30)
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf"), r.content[:8]
    cabecalho = r.content.decode("utf-8-sig").splitlines()[0]
    assert ";" in cabecalho and cabecalho.count(";") >= 3, cabecalho


# ---------------------------------------------------------------- relatório mensal ---
def test_relatorio_mensal_html_declara_os_alertas_simulados(demo, sessao):
    r = sessao.get(demo.base + "/relatorio/mensal", timeout=60)
    assert r.status_code == 200
    assert re.search(r"alertas? simulados?", r.text), "o relatório não avisa que inclui histórico de demonstração"


# ------------------------------------------------------------------- tema escuro ---
def test_gestao_no_tema_escuro(navegador, demo):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    contexto.add_init_script("try{localStorage.setItem('visionepi-theme','dark')}catch(e){}")
    pagina = contexto.new_page()
    try:
        entrar(pagina, demo, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"Câmeras|Início")).first.wait_for(timeout=60_000)
        pagina.goto(demo.base + "/gestao")
        pagina.locator("[data-testid=gestao]").wait_for(timeout=30_000)
        assert pagina.evaluate("document.documentElement.dataset.theme") == "dark"
        fundo = pagina.evaluate("getComputedStyle(document.body).backgroundColor")
        r, g, b = (int(x) for x in re.findall(r"\d+", fundo)[:3])
        assert r + g + b < 120, fundo
    finally:
        contexto.close()
