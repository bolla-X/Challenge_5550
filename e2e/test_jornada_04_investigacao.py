"""Jornada 4 (MISSÃO 4, Fase 5 item 3): a investigação, da busca nas trilhas ao simulador "E se?".

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py), na câmera "Multidão":

1. `/busca`: busca nas trilhas gravadas por "sem capacete" (EPI ausente) -> resultado com um rótulo de rastreio
   ("Pessoa N", nunca identidade) -> "Ver trilha" desenha a trilha e, quando o servidor achou um clipe no período,
   "Abrir replay" abre o replay do incidente;
2. `/simulador`: a regra proposta é editada (a histerese vai ao máximo) e "Reprocessar" mostra o resultado
   comparativo (proposta x hoje simulado x o que de fato disparou), sem mudar alerta real.

Timeouts generosos para esta máquina lenta: login 60 s; trilha gravada até 240 s (a busca lê a trilha que a
câmera grava); reprocessamento 120 s.
"""

from __future__ import annotations

import re

from conftest import entrar, esperar


def test_investigacao_busca_nas_trilhas_e_simulador_com_regra_editada(navegador, servidor):
    tecnico = servidor.sessao("technical")
    multidao = servidor.cameras["Multidão"]
    # A busca e o simulador leem a trilha que a câmera grava: sem trilha gravada com gente sem capacete não há o que achar.
    esperar(lambda: tecnico.get(f"{servidor.base}/api/busca/trilhas", params={"camera_id": multidao, "epi_ausente": "helmet"},
                                timeout=60).json().get("total", 0) >= 1, 240, 3,
            msg="a trilha da Multidão não tem ninguém sem capacete")
    esperar(lambda: (tecnico.get(f"{servidor.base}/api/simulador/contexto", params={"camera_id": multidao}, timeout=30)
                     .json().get("trilha") or {}).get("registros", 0) > 0, 240, 3, msg="o simulador não tem trilha gravada da Multidão")
    reais_antes = tecnico.get(f"{servidor.base}/alerts", params={"camera_id": multidao, "limit": 500}, timeout=20).json()["count"]

    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Sair").wait_for(timeout=60_000)

        # 1. Busca: trilhas da Multidão sem capacete.
        pagina.goto(servidor.base + "/busca")
        pagina.locator("[data-testid=busca-trilhas]").wait_for(timeout=60_000)
        pagina.get_by_label("Câmera", exact=True).select_option(str(multidao))
        pagina.get_by_role("checkbox", name="Capacete").check()
        pagina.locator("[data-testid=busca-filtrar]").click()
        pagina.locator("[data-testid=busca-estado][data-estado=pronto]").wait_for(timeout=60_000)
        resultados = pagina.locator("[data-testid=busca-resultado]")
        resultados.first.wait_for(timeout=15_000)
        rotulo = resultados.first.get_attribute("data-rotulo") or ""
        assert re.fullmatch(r"Pessoa \S+", rotulo), rotulo
        assert "Sem capacete" in resultados.first.inner_text(), resultados.first.inner_text()
        assert "Câmera Multidão" in pagina.locator("[data-testid=busca-estado]").inner_text()

        # ... a trilha desenhada: um desenho acessível com o rótulo, o horário e os pontos.
        resultados.first.get_by_role("button", name="Ver trilha").click()
        trilha = resultados.first.locator("[data-testid=busca-trilha]")
        trilha.wait_for(timeout=15_000)
        assert re.search(r"Trilha de Pessoa \S+", trilha.get_by_role("img").first.get_attribute("aria-label") or "")

        # ... e o replay, quando o servidor achou um clipe gravado no período.
        com_replay = pagina.locator("[data-testid=busca-replay]")
        if com_replay.count():
            com_replay.first.click()
            canvas = pagina.locator('canvas[aria-label="Replay do incidente"]')
            canvas.wait_for(timeout=30_000)
            assert int(canvas.get_attribute("data-total") or 0) > 1, "clipe sem quadros"
            pagina.get_by_role("dialog").last.get_by_role("button", name="Fechar").click()
            canvas.wait_for(state="detached", timeout=15_000)

        # 2. Simulador: edita a regra (histerese no máximo) e compara.
        pagina.goto(f"{servidor.base}/simulador?camera={multidao}")
        pagina.locator("[data-testid=simulador]").wait_for(timeout=60_000)
        rodar = pagina.locator("[data-testid=sim-rodar]")
        rodar.wait_for(timeout=60_000)
        esperar(lambda: rodar.is_enabled(), 120, 1, msg="o botão Reprocessar não liberou (sem trilha carregada)")
        histerese = pagina.locator("[data-testid=sim-histerese]")
        histerese.focus()
        pagina.keyboard.press("End")  # sobe a histerese ao máximo (10 s), pelo teclado
        assert re.search(r"Histerese para criar:\s*10(,0)?\s*s", pagina.locator("[data-testid=simulador]").inner_text()), \
            "a histerese editada não apareceu na regra proposta"
        rodar.click()
        pagina.locator("[data-testid=sim-numeros]").wait_for(timeout=120_000)
        total = pagina.locator("[data-testid=sim-total]")
        real = pagina.locator("[data-testid=sim-real]")
        assert int(total.get_attribute("data-valor")) >= 0 and int(real.get_attribute("data-valor")) >= 0
        numeros = pagina.locator("[data-testid=sim-numeros]").inner_text()
        for rotulo in ("Teriam disparado", "Dispararam de fato", "Regra de hoje, simulada"):
            assert rotulo in numeros, numeros
        assert pagina.get_by_role("columnheader", name="Proposta", exact=True).count() == 1
        assert pagina.get_by_role("columnheader", name="Real", exact=True).count() == 1
    finally:
        contexto.close()
    # O simulador reprocessa; nunca apaga nem resolve alerta real.
    reais_depois = tecnico.get(f"{servidor.base}/alerts", params={"camera_id": multidao, "limit": 500}, timeout=20).json()["count"]
    assert reais_depois >= reais_antes, (reais_antes, reais_depois)
