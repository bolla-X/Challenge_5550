"""Jornada 5 (MISSÃO 4, Fase 5 item 3): a evacuação pela tela, do acionamento ao elo na cadeia de custódia.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). O supervisor aciona o Modo Evacuação
(com confirmação), vê o cronômetro andar e o aviso de dupla contagem, encerra e salva o relatório, e o relatório
vira um elo `evacuacao` na cadeia de custódia, que continua íntegra.

Timeouts generosos para esta máquina lenta: login 60 s; a tela de evacuação 60 s; cada passo 30 s.
Movida de e2e/test_missao4.py (M3), trocando o `time.sleep(3)` do cronômetro por espera por condição.
(Que operador e técnico NÃO acionam continua em test_missao4.py::test_m3_operador_nao_aciona.)
"""

from __future__ import annotations

from conftest import entrar, esperar


def test_evacuacao_pela_tela_ate_o_relatorio_na_custodia(navegador, servidor):
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
        esperar(lambda: crono.inner_text() != primeiro, 15, 0.5, msg="o cronômetro não anda")
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
