"""Nenhum texto de obra na tela (MISSÃO 2, Fase C): "em construção", TODO, lorem, placeholder, travessão.

Passa por todas as rotas logado como supervisor e lê o texto visível. O
travessão (—) entra na lista porque o sistema de design o proíbe em texto
visível (docs/NEXT2026/DESIGN.md); separador é vírgula, dois pontos ou ponto
médio (no máximo um por linha).
"""

from __future__ import annotations

import re

from conftest import entrar

PROIBIDOS = re.compile(r"em constru[çc][ãa]o|\bTODO\b|lorem ipsum|\bplaceholder\b|\bFIXME\b|—", re.IGNORECASE)


def _rotas(servidor):
    canteiro = servidor.cameras["Canteiro"]
    return ["/", "/gemeo", "/gemeo?2d=1", f"/simulador?camera={servidor.cameras['Multidão']}", "/auditoria", "/liga",
            "/retrospectiva", "/retrospectiva?periodo=semana", "/palco", "/tv", f"/portal?camera={canteiro}",
            f"/portal?camera={canteiro}&desafio=1", "/rotular", "/desafio", "/relatorio/turno",
            # MISSÃO 4
            "/torre", "/evacuacao", "/regras", "/permissoes", "/ajuda", "/status", "/novidades", "/configuracoes",
            "/busca", "/intervencoes", "/relatorio/mensal", "/primeiro-acesso", "/caixa-de-entrada"]


# Frase exigida LITERALMENTE pela MISSÃO 4 (M3), com travessão: é a única exceção à regra do sistema de design.
EXCECOES = ("contagem por câmera — pode haver dupla contagem",)


def test_nenhum_texto_de_obra_em_rota_nenhuma(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    achados: dict[str, list[str]] = {}
    try:
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)
        for rota in _rotas(servidor):
            pagina.goto(servidor.base + rota)
            pagina.wait_for_timeout(3000)
            texto = pagina.inner_text("body")
            linhas = [ln.strip() for ln in texto.splitlines()
                      if PROIBIDOS.search(ln) and not any(e in ln.lower() for e in EXCECOES)]
            if linhas:
                achados[rota] = linhas[:5]
        # Tela de foco (a mais densa), aba a aba.
        pagina.goto(servidor.base + "/")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
        pagina.get_by_role("button", name="Configurar Multidão").click(timeout=30_000)
        for aba in pagina.get_by_role("tab").all():
            aba.click()
            pagina.wait_for_timeout(800)
            linhas = [ln.strip() for ln in pagina.inner_text("body").splitlines() if PROIBIDOS.search(ln)]
            if linhas:
                achados[f"foco:{aba.inner_text()}"] = linhas[:5]
    finally:
        contexto.close()
    assert not achados, achados
