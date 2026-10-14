"""Acessibilidade (MISSÃO 2, portão): axe-core em todas as rotas, nos dois temas.

Falha com qualquer violação de impacto "serious" ou "critical". O axe-core
(MPL-2.0) é dependência de desenvolvimento do frontend
(`frontend/node_modules/axe-core/axe.min.js`); sem ele, o teste é pulado com a
instrução de como instalar. O relatório completo (todas as violações, inclusive
"moderate"/"minor") vai para `bench/runtime/axe-<tema>.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import RAIZ, entrar

AXE = RAIZ / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def _rotas(servidor) -> list[tuple[str, str]]:
    canteiro = servidor.cameras["Canteiro"]
    return [
        ("grade", "/"),
        ("gemeo", "/gemeo"),
        ("gemeo-2d", "/gemeo?2d=1"),
        ("simulador", f"/simulador?camera={servidor.cameras['Multidão']}"),
        ("auditoria", "/auditoria"),
        ("liga", "/liga"),
        ("retrospectiva", "/retrospectiva"),
        ("palco", "/palco"),
        ("tv", "/tv"),
        ("portal", f"/portal?camera={canteiro}"),
        ("portal-desafio", f"/portal?camera={canteiro}&desafio=1"),
        ("rotular", "/rotular"),
        ("desafio", "/desafio"),
    ]


def _axe(pagina) -> list[dict]:
    pagina.add_script_tag(path=str(AXE))
    resultado = pagina.evaluate(
        """() => axe.run(document, {resultTypes: ['violations'],
                 runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']}})"""
    )
    return [
        {"id": v["id"], "impact": v["impact"], "help": v["help"], "nodes": [n["target"] for n in v["nodes"]][:5]}
        for v in resultado["violations"]
    ]


@pytest.mark.parametrize("tema", ["light", "dark"])
def test_axe_sem_violacao_seria_ou_critica(navegador, servidor, tema):
    if not AXE.exists():
        pytest.skip("axe-core ausente: npm --prefix frontend ci")
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768}, color_scheme=tema)
    contexto.add_init_script(f"try{{localStorage.setItem('visionepi-theme','{tema}')}}catch(e){{}}")
    relatorio: dict[str, list[dict]] = {}
    try:
        pagina = contexto.new_page()
        pagina.goto(servidor.base + "/")
        pagina.get_by_label("E-mail").wait_for(timeout=60_000)
        relatorio["login"] = _axe(pagina)
        entrar(pagina, servidor, "supervisor")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)
        for nome, rota in _rotas(servidor):
            pagina.goto(servidor.base + rota)
            pagina.wait_for_timeout(3500)
            relatorio[nome] = _axe(pagina)
        # Tela de foco de uma câmera (a mais densa do painel).
        pagina.goto(servidor.base + "/")
        pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=30_000)
        pagina.get_by_role("button", name="Configurar Canteiro").click(timeout=30_000)
        pagina.wait_for_timeout(3500)
        relatorio["foco"] = _axe(pagina)
        # Controle do palco no celular (sem login, token do QR).
        pagina.goto(servidor.base + "/palco")
        url = pagina.locator("[data-testid=palco-qr]").get_attribute("data-url", timeout=30_000)
        celular = navegador.new_context(viewport={"width": 390, "height": 844}, color_scheme=tema)
        try:
            fone = celular.new_page()
            fone.goto(servidor.base + url[url.index("/palco/controle"):])
            fone.locator("[data-testid=controle-cena]").wait_for(timeout=30_000)
            relatorio["palco-controle"] = _axe(fone)
        finally:
            celular.close()
    finally:
        contexto.close()
    saida = RAIZ / "bench" / "runtime" / f"axe-{tema}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    graves = {rota: [v for v in vs if v["impact"] in ("serious", "critical")] for rota, vs in relatorio.items()}
    graves = {r: v for r, v in graves.items() if v}
    assert not graves, json.dumps(graves, indent=1, ensure_ascii=False)[:6000]


def test_axe_disponivel_no_ambiente_de_desenvolvimento():
    """O portão exige o axe: se o módulo sumir do package.json, este teste avisa."""
    pacote = json.loads(Path(RAIZ / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert "axe-core" in pacote.get("devDependencies", {})
