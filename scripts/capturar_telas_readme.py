"""Gera as capturas do README e do manual de uso (`docs/img/`) com o Playwright, no modo demonstração.

    python scripts/capturar_telas_readme.py

Sobe `run.py --demo` deste checkout (sem webcam), espera o Pátio ter alerta e segunda
opinião, e fotografa as telas citadas em docs/manual-de-uso.md, 1440x900, tema claro
(a última, no escuro). PNG otimizado pelo próprio Chromium; nada de dado real: a demo
usa gravações públicas e dados simulados.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "e2e"))
sys.path.insert(0, str(RAIZ / "scripts" / "video"))

from fumaca_demo import DemoEm  # noqa: E402
from gravar_demo import _aquecer  # noqa: E402

DESTINO = RAIZ / "docs" / "img"
TAMANHO = {"width": 1440, "height": 900}
PREPARO = ("try{localStorage.setItem('visionepi-theme', %r);"
           "['operator','technical','supervisor'].forEach(p=>localStorage.setItem('visionepi-tour-visto-'+p,'1'))}catch(e){}")


def _foto(pagina, nome: str) -> None:
    time.sleep(1.2)
    pagina.screenshot(path=str(DESTINO / nome))
    print(f"[capturas] docs/img/{nome}", flush=True)


def _entrar(pagina, demo: DemoEm) -> None:
    pagina.goto(demo.base + "/")
    pagina.get_by_label("E-mail").wait_for(timeout=60_000)
    pagina.get_by_label("E-mail").fill(demo.emails["supervisor"])
    pagina.get_by_label("Senha").fill(demo.senhas["supervisor"])
    pagina.get_by_role("button", name="Entrar").click()
    pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.wait_for(timeout=60_000)


def _aba_do_foco(pagina, rotulo: str) -> None:
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


def capturar(demo: DemoEm) -> None:
    from playwright.sync_api import sync_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=True)
        try:
            ctx = nav.new_context(viewport=TAMANHO)
            ctx.add_init_script(PREPARO % "light")
            p = ctx.new_page()
            p.goto(demo.base + "/")
            p.get_by_label("E-mail").wait_for(timeout=60_000)
            _foto(p, "01-login.png")
            _entrar(p, demo)
            _foto(p, "02-inicio-supervisor.png")
            p.get_by_role("button", name=re.compile(r"^Câmeras")).first.click()
            p.locator("canvas.live-video").first.wait_for(timeout=30_000)
            time.sleep(4)
            _foto(p, "03-grade-cameras.png")
            p.get_by_role("button", name=re.compile("Configurar Pátio")).click()
            p.locator("[role=tablist]").first.wait_for(timeout=30_000)
            time.sleep(4)
            _foto(p, "04-foco-camera.png")
            _aba_do_foco(p, "Alertas")
            p.locator("[data-testid=incidente]").first.wait_for(timeout=120_000)
            _foto(p, "05-incidentes.png")
            _aba_do_foco(p, "Segunda opinião")
            p.locator("[data-testid=llm-modo-demonstracao]").wait_for(timeout=30_000)
            _foto(p, "13-status-llm-demo.png")

            p.goto(demo.base + "/gestao")
            p.locator("[data-testid=gestao]").wait_for(timeout=30_000)
            p.locator("[data-testid=gestao-aba-colaboradores]").click()
            p.locator("[data-testid^=gestao-colaborador-]").first.wait_for(timeout=30_000)
            _foto(p, "06-gestao-colaboradores.png")
            p.locator("[data-testid^=gestao-colaborador-]").nth(2).click()
            p.locator("[data-testid=gestao-historico]").wait_for(timeout=30_000)
            p.locator("[data-testid=gestao-historico]").scroll_into_view_if_needed()
            _foto(p, "07-gestao-historico.png")
            p.locator("[data-testid=gestao-aba-catalogo]").click()
            p.locator("[data-testid=gestao-tabela-epis]").wait_for(timeout=30_000)
            _foto(p, "08-gestao-catalogo.png")
            p.locator("[data-testid=gestao-aba-entregas]").click()
            p.locator("[data-testid=gestao-tabela-entregas]").wait_for(timeout=30_000)
            _foto(p, "09-gestao-entregas.png")
            p.locator("[data-testid=gestao-aba-ocorrencias]").click()
            p.locator("[data-testid=gestao-tabela-ocorrencias]").wait_for(timeout=30_000)
            _foto(p, "10-gestao-ocorrencias.png")
            p.locator("[data-testid=gestao-aba-relatorios]").click()
            p.locator("[data-testid=gestao-resumo]").wait_for(timeout=30_000)
            _foto(p, "11-gestao-exportar.png")
            p.goto(demo.base + "/relatorio/mensal")
            p.wait_for_load_state("load")
            _foto(p, "12-relatorio-mensal.png")
            ctx.close()

            escuro = nav.new_context(viewport=TAMANHO)
            escuro.add_init_script(PREPARO % "dark")
            p = escuro.new_page()
            _entrar(p, demo)
            p.goto(demo.base + "/gestao?aba=catalogo")
            p.locator("[data-testid=gestao-tabela-epis]").wait_for(timeout=30_000)
            _foto(p, "14-tema-escuro.png")
            escuro.close()
        finally:
            nav.close()


def main() -> int:
    python = RAIZ / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    demo = DemoEm(RAIZ, python)
    demo.subir()
    try:
        _aquecer(demo)
        capturar(demo)
    finally:
        demo.parar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
