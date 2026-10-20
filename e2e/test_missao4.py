"""E2E da MISSÃO 4 que NÃO são jornada: permissões por papel, editor de regras, páginas de exceção e rotas novas.

As jornadas ponta a ponta (primeiro acesso, turno do operador, incidente, investigação, evacuação,
permissão com vigia, integração industrial, sabotagem, gamificação e apresentação) moraram aqui e agora
estão uma por arquivo em `e2e/test_jornada_NN_*.py`. O que ficou:

- M1: só o técnico redefine a referência da saúde visual;
- M2: o operador vê só a própria câmera na torre;
- M3: operador e técnico não acionam a evacuação (só o supervisor);
- M4: regra do editor criada na API, testada no histórico e disparando ao vivo;
- M5: o operador lê, mas não emite, permissão de trabalho;
- as rotas novas abrem sem erro de console;
- Fase 3 item 9: a 404 desenhada, a sessão que expira sozinha (a tela consulta a API e leva 401) e a faixa de "sem conexão".

Contra o servidor REAL com 4 câmeras de fixture (ver e2e/conftest.py). Timeouts generosos para esta máquina
lenta (login 60 s; alerta ao vivo até 240 s).
"""

from __future__ import annotations

import pytest

from conftest import alertas_ativos, entrar, esperar


def test_m1_redefinir_referencia_so_tecnico(servidor):
    cid = servidor.cameras["Canteiro"]
    url = f"{servidor.base}/api/cameras/{cid}/saude-visual/referencia"
    assert servidor.sessao("operator").post(url, timeout=20).status_code in (403, 404)
    r = servidor.sessao("technical").post(url, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["tem_referencia"] is True and r.json()["estado"] == "ok"


def test_m2_operador_ve_so_a_propria_camera_na_torre(servidor):
    corpo = servidor.sessao("operator").get(f"{servidor.base}/api/integracao/estado", timeout=20).json()
    ids = {c["id"] for c in corpo["planta"]["cameras"]}
    assert ids <= {servidor.cameras["Multidão"]}, ids


def test_m3_operador_nao_aciona(servidor):
    assert servidor.sessao("operator").post(f"{servidor.base}/api/evacuacao/iniciar", json={}, timeout=20).status_code == 403
    assert servidor.sessao("technical").post(f"{servidor.base}/api/evacuacao/iniciar", json={}, timeout=20).status_code == 403


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
    teste = esperar(lambda: (r := tecnico.post(f"{servidor.base}/api/regras/testar",
                                                json={"regra": regra, "camera_id": multidao, "horas": 1}, timeout=60))
                     .status_code == 200 and r.json(), 180, 3, msg="teste no histórico não respondeu 200")
    assert teste["simulavel"] is True, teste
    assert teste["disparos"] >= 1, teste
    criada = tecnico.post(f"{servidor.base}/api/regras", json=regra, timeout=20)
    assert criada.status_code == 201, criada.text
    rid = criada.json()["regra"]["id"]
    try:
        assert tecnico.post(f"{servidor.base}/api/regras/{rid}/ativar", timeout=20).status_code == 200
        esperar(lambda: any(a.get("rule") == f"regra:{rid}" for a in alertas_ativos(tecnico, servidor, "Multidão")), 240,
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
        esperar(lambda: "sem rede" in faixa.inner_text().lower(), 15, 0.5, msg="faixa de sem conexão não apareceu")
        contexto.set_offline(False)
        esperar(lambda: not faixa.inner_text().strip(), 60, 1, msg="faixa de sem conexão não sumiu")
    finally:
        contexto.close()


@pytest.mark.parametrize("papel", ["technical", "supervisor"])
def test_barra_superior_cabe_no_celular(navegador, servidor, papel):
    """390×844: os atalhos da barra ficam só no "Menu" (nada de "Buscar"/"Mais" soltos), a barra cabe na largura e
    "Sair" continua visível. Regressão: a regra do "Mais" no missao4.css anulava o `display: none` do celular."""
    contexto = navegador.new_context(viewport={"width": 390, "height": 844})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, papel)
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
        medida = pagina.evaluate("""() => {
          const vis = (el) => !!el && el.getBoundingClientRect().width > 0 && getComputedStyle(el).display !== 'none';
          const sair = [...document.querySelectorAll('.appbar button')].find((b) => b.textContent.trim() === 'Sair');
          const r = sair.getBoundingClientRect();
          // Quem passa da borda direita (para o relatório da falha dizer a causa).
          const estouram = [...document.querySelectorAll('body *')]
            .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 0.5 && vis(el))
            .filter((el, _i, todos) => !todos.some((outro) => outro !== el && el.contains(outro)))
            .slice(0, 6)
            .map((el) => el.tagName.toLowerCase() + '.' + [...el.classList].join('.') + ' → '
                         + Math.round(el.getBoundingClientRect().right));
          return {secundarios: vis(document.querySelector('.appbar-secundarios')),
                  menu: vis(document.querySelector('.appbar-menu')),
                  largura: document.documentElement.scrollWidth,
                  sair_dentro: r.left >= 0 && r.right <= window.innerWidth, estouram};
        }""")
        estouram = medida.pop("estouram")
        assert medida == {"secundarios": False, "menu": True, "largura": 390, "sair_dentro": True}, (medida, estouram)
    finally:
        contexto.close()


def test_mais_alinhado_com_os_outros_atalhos_da_barra(pagina, servidor):
    """Desktop: "Mais" (summary de um <details>) fica na mesma linha de "Buscar" e "Relatório do turno"."""
    entrar(pagina, servidor, "technical")
    pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)
    medida = pagina.evaluate("""() => {
      const centro = (el) => { const r = el.getBoundingClientRect(); return Math.round((r.top + r.bottom) / 2); };
      const fonte = (el) => getComputedStyle(el).fontSize + ' ' + getComputedStyle(el).fontWeight;
      const mais = document.querySelector('[data-testid=menu-mais]');
      const buscar = [...document.querySelectorAll('.appbar-secundarios > button')].find((b) => b.textContent.includes('Buscar'));
      const caixa = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        return [Math.round(r.top), Math.round(r.height), s.display, s.marginTop, s.marginBottom, s.alignSelf].join(' '); };
      return {mais: centro(mais), buscar: centro(buscar), fonte_mais: fonte(mais), fonte_buscar: fonte(buscar),
              diag: {details: caixa(mais.parentElement), summary: caixa(mais), buscar: caixa(buscar),
                     grupo: caixa(mais.parentElement.parentElement)}};
    }""")
    diag = medida.pop("diag")
    assert abs(medida["mais"] - medida["buscar"]) <= 1 and medida["fonte_mais"] == medida["fonte_buscar"], (medida, diag)


def test_produto_cabe_no_celular(navegador, servidor):
    """/produto (público) em 390×844: nada passa da largura. Regressão: `a.button.primary` vencia o `display: none`
    do botão do topo no celular e cortava "Falar com a equipe" na borda."""
    contexto = navegador.new_context(viewport={"width": 390, "height": 844})
    try:
        pagina = contexto.new_page()
        pagina.goto(servidor.base + "/produto")
        pagina.get_by_role("heading", level=1).wait_for(timeout=60_000)
        largura = pagina.evaluate("() => document.documentElement.scrollWidth")
        assert largura == 390, largura
    finally:
        contexto.close()
