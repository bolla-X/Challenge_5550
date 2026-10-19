"""Jornada 3 (MISSÃO 4, Fase 5 item 3): o incidente completo, do alerta ao relatório do turno.

Contra o servidor REAL com 4 câmeras de fixture (e2e/conftest.py), na câmera "Multidão":

1. um alerta nasce e vira UM incidente agrupado (`/api/incidentes?status=active`): vários alertas por pessoa,
   um incidente por (regra, zona);
2. o técnico abre o incidente na aba Alertas da câmera ("Linha causal"), vê a linha causal por ID de rastreio
   e abre o replay do incidente (o clipe tem de existir e tocar);
3. "Verificar integridade" da cadeia de custódia responde íntegra;
4. o relatório do turno (`/relatorio/turno`) lista o tipo do incidente e a câmera.

Timeouts generosos para esta máquina lenta: login 60 s; incidente ao vivo até 240 s; clipe do replay até 240 s
(ele só fecha depois do alerta).
"""

from __future__ import annotations

import re

from conftest import entrar, esperar

LINHA_CAUSAL = re.compile(r"apareceu|entrou|estava na|aproximou")


def _incidentes_ativos(sessao, servidor, camera_id: int) -> list[dict]:
    r = sessao.get(f"{servidor.base}/api/incidentes", params={"status": "active", "camera_id": camera_id}, timeout=20)
    r.raise_for_status()
    return r.json()["items"]


def _posicao_do_clipe(sessao, servidor, alertas: list[dict]) -> int | None:
    """Posição do primeiro alerta cujo clipe de replay já existe (o clipe só fecha depois do alerta)."""
    for i, alerta in enumerate(alertas):
        if sessao.get(f"{servidor.base}/api/alerts/{alerta['id']}/clip", timeout=20).status_code == 200:
            return i
    return None


def test_incidente_completo_do_alerta_ao_relatorio_do_turno(navegador, servidor):
    tecnico = servidor.sessao("technical")
    multidao = servidor.cameras["Multidão"]

    # 1. Alerta -> incidente agrupado.
    incidentes = esperar(lambda: _incidentes_ativos(tecnico, servidor, multidao), 240, 2,
                         msg="a Multidão não abriu nenhum incidente ativo")
    chaves = [(i["rule"], i["zona"]) for i in incidentes]
    assert len(chaves) == len(set(chaves)), f"mais de um incidente ativo para a mesma regra e zona: {chaves}"
    assert all(i["alert_ids"] and i["camera_id"] == multidao for i in incidentes), incidentes
    alertas = esperar(lambda: [a for a in tecnico.get(f"{servidor.base}/alerts", params={"camera_id": multidao, "status": "active"},
                                                      timeout=20).json()["items"]], 120, 2, msg="nenhum alerta ativo na Multidão")
    assert len(alertas) >= 1

    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "technical")
        pagina.get_by_role("button", name="Configurar Multidão").click(timeout=60_000)
        pagina.locator("[role=tablist]").first.wait_for(timeout=30_000)
        aba = pagina.get_by_role("tab", name="Alertas")
        if aba.count():
            aba.click()
        else:
            pagina.locator(".tabs-more > button").click()
            pagina.get_by_role("menuitem", name="Alertas").click()

        # 2. Abre o incidente da lista: o cabeçalho dele carrega o id e o título; a linha causal narra por ID de rastreio.
        resumo = pagina.locator("[data-testid=incidente]").first
        resumo.wait_for(timeout=240_000)
        incidente_id = int(resumo.get_attribute("data-incidente"))
        titulo = resumo.get_attribute("data-titulo")
        pagina.locator("[data-testid=incidente-abrir]").first.click()
        detalhe = pagina.locator("[data-testid=incidente-detalhe]")
        detalhe.wait_for(timeout=15_000)
        passos = pagina.locator("[data-testid=linha-causal] li")
        passos.first.wait_for(timeout=30_000)
        assert LINHA_CAUSAL.search(passos.first.inner_text()), passos.first.inner_text()

        # 3. Replay do incidente: espera um clipe pronto (API) entre os alertas que a tela lista, abre o botão
        #    desse alerta e vê os quadros andarem.
        botoes = detalhe.get_by_role("button", name="Ver replay")
        botoes.first.wait_for(timeout=30_000)
        listados = botoes.count()
        alertas_do_incidente = tecnico.get(f"{servidor.base}/api/incidentes/{incidente_id}", timeout=20).json()["alertas"][:listados]
        achado = esperar(lambda: (p := _posicao_do_clipe(tecnico, servidor, alertas_do_incidente)) is not None and (p,),
                         240, 3, msg="nenhum alerta do incidente ganhou clipe de replay")
        posicao = achado[0]
        detalhe.get_by_role("button", name="Ver replay").nth(posicao).click()
        canvas = pagina.locator('canvas[aria-label="Replay do incidente"]')
        canvas.wait_for(timeout=30_000)
        assert int(canvas.get_attribute("data-total") or 0) > 1, "clipe sem quadros"
        primeiro = int(canvas.get_attribute("data-quadro") or 0)
        esperar(lambda: int(canvas.get_attribute("data-quadro") or 0) != primeiro, 15, 0.3, msg="o replay não avançou")
        pagina.get_by_role("dialog").last.get_by_role("button", name="Fechar").click()
        canvas.wait_for(state="detached", timeout=15_000)

        # 4. Verificar integridade da custódia: íntegra, sem adulteração.
        detalhe.locator("[data-testid=verificar-integridade]").click()
        resultado = detalhe.locator("[data-testid=custodia-resultado]")
        resultado.wait_for(timeout=60_000)
        assert "Adulteração" not in resultado.inner_text(), resultado.inner_text()
        assert resultado.get_attribute("data-integra") == "1", resultado.inner_text()

        # 5. Relatório do turno: o tipo do incidente e a câmera aparecem nos números.
        pagina.goto(servidor.base + "/relatorio/turno?horas=2")
        pagina.get_by_role("heading", name="Relatório de turno").wait_for(timeout=30_000)
        pagina.get_by_role("cell", name=titulo, exact=True).first.wait_for(timeout=15_000)
        pagina.get_by_role("cell", name="Multidão", exact=True).first.wait_for(timeout=15_000)
    finally:
        contexto.close()
    # A mesma informação pela API do relatório (o que a página imprime vem do banco).
    relatorio = tecnico.get(f"{servidor.base}/api/relatorio/turno", params={"horas": 2}, timeout=20).json()["alertas"]
    assert relatorio["por_regra"].get(titulo, 0) >= 1, relatorio["por_regra"]
    assert relatorio["por_camera"].get("Multidão", 0) >= 1, relatorio["por_camera"]
