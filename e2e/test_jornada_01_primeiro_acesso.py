"""Jornada 1 (MISSÃO 4, Fase 5 item 3): o primeiro acesso do supervisor até "pronto para operar".

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py). O assistente do `/primeiro-acesso` é
percorrido pela tela, passo a passo, e a conta do operador nasce no passo de usuários, com a senha
temporária mostrada uma única vez.

Timeouts generosos para esta máquina lenta: login 60 s; cada passo do assistente 30 s.
Movida de e2e/test_missao4.py (sem duplicar).
"""

from __future__ import annotations

import time

from conftest import entrar, esperar


def test_primeiro_acesso_do_supervisor_ate_pronto_para_operar(navegador, servidor):
    """Assistente do início ao checklist "pronto para operar", com a conta criada no passo de usuários
    e a senha temporária exibida uma única vez."""
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
            esperar(lambda n=nome: pagina.locator("[data-testid=onb-passo]").get_attribute("data-passo") != n
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
