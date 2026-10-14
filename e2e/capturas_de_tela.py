"""Capturas de tela de todas as telas, nos dois temas e em duas resoluções.

    python e2e/capturas_de_tela.py                 # grava em bench/runtime/capturas/
    python e2e/capturas_de_tela.py --so 1366x768-claro

Sobe o MESMO servidor do E2E (fixtures, 3 papéis, senhas geradas e nunca
impressas) e percorre as telas como cada papel. As imagens ficam fora do git
(`bench/runtime/` é ignorado): têm pessoas das fixtures, ainda que com o rosto
desfocado pelo modo privacidade.

Serve para a revisão visual do PR2 (MISSAO.md, Fase 2, item 6): cor só para
status, tema claro como padrão da demo, nada quebrando em 1366x768.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import ServidorE2E, entrar  # noqa: E402

DESTINO = RAIZ / "bench" / "runtime" / "capturas"
TAMANHOS = {"1920x1080": (1920, 1080), "1366x768": (1366, 768)}
TEMAS = {"claro": "light", "escuro": "dark"}


def _abrir_aba(pagina, rotulo: str) -> None:
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


def _foto(pagina, pasta: Path, nome: str) -> None:
    pagina.wait_for_timeout(1200)  # animações curtas e o primeiro quadro do vídeo
    pagina.screenshot(path=str(pasta / f"{nome}.png"), full_page=False)


def capturar(servidor: ServidorE2E, navegador, pasta: Path, largura: int, altura: int, tema: str) -> list[str]:
    pasta.mkdir(parents=True, exist_ok=True)
    feitas: list[str] = []

    def contexto():
        ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=tema)
        ctx.add_init_script(f"try {{ localStorage.setItem('visionepi-theme', '{tema}'); }} catch (e) {{}}")
        return ctx

    # Sem login.
    ctx = contexto()
    pg = ctx.new_page()
    pg.goto(servidor.base + "/")
    _foto(pg, pasta, "01-login")
    feitas.append("01-login")
    ctx.close()

    # Técnico: grade, foco e abas.
    ctx = contexto()
    pg = ctx.new_page()
    entrar(pg, servidor, "technical")
    pg.locator("canvas.live-video, .camera-card, img").first.wait_for(timeout=30_000)
    _foto(pg, pasta, "02-tecnico-grade")
    pg.get_by_role("button", name="Configurar Multidão").click(timeout=30_000)
    pg.locator("canvas.live-video").first.wait_for(timeout=30_000)
    time.sleep(4)
    _foto(pg, pasta, "03-tecnico-foco")
    for i, aba in enumerate(["Alertas", "Pessoas", "Diagnóstico", "Mapa de calor", "Config. câmera"], start=4):
        try:
            _abrir_aba(pg, aba)
            nome = f"{i:02d}-tecnico-aba-{re.sub(r'[^a-z]+', '-', aba.lower()).strip('-')}"
            _foto(pg, pasta, nome)
            feitas.append(nome)
        except Exception as exc:  # noqa: BLE001  (registra e segue: é inventário visual)
            print(f"  aba {aba}: {exc}")
    feitas += ["02-tecnico-grade", "03-tecnico-foco"]
    for nome, abrir in [
        ("13-tecnico-sobre", lambda: pg.get_by_role("button", name="Sobre", exact=True).click()),
        ("14-tecnico-prova-de-escala", lambda: pg.get_by_role("button", name="Prova de escala").click()),
    ]:
        try:
            if nome.endswith("escala"):
                pg.goto(servidor.base + "/")
                pg.get_by_role("button", name="Prova de escala").wait_for(timeout=30_000)
            abrir()
            _foto(pg, pasta, nome)
            feitas.append(nome)
        except Exception as exc:  # noqa: BLE001
            print(f"  {nome}: {exc}")
    pg.goto(servidor.base + "/relatorio/turno")
    _foto(pg, pasta, "09-relatorio-turno")
    feitas.append("09-relatorio-turno")
    ctx.close()

    # Supervisor: início e contas.
    ctx = contexto()
    pg = ctx.new_page()
    entrar(pg, servidor, "supervisor")
    pg.wait_for_timeout(2000)
    _foto(pg, pasta, "10-supervisor-inicio")
    feitas.append("10-supervisor-inicio")
    for nome, rotulo in [("15-supervisor-contas", "Contas"), ("16-supervisor-visao-geral", "Câmeras")]:
        try:
            pg.goto(servidor.base + "/")
            pg.get_by_role("button", name=rotulo).first.click(timeout=30_000)
            if rotulo == "Câmeras":
                pg.get_by_role("button", name="Visão geral").click(timeout=30_000)
            _foto(pg, pasta, nome)
            feitas.append(nome)
        except Exception as exc:  # noqa: BLE001
            print(f"  {nome}: {exc}")
    ctx.close()

    # Operador: quiosque da câmera do setor.
    ctx = contexto()
    pg = ctx.new_page()
    entrar(pg, servidor, "operator")
    pg.locator("canvas.live-video").first.wait_for(timeout=30_000)
    time.sleep(3)
    _foto(pg, pasta, "11-operador-quiosque")
    feitas.append("11-operador-quiosque")
    ctx.close()

    # Telas de tela cheia do PR3 (técnico).
    ctx = contexto()
    pg = ctx.new_page()
    entrar(pg, servidor, "technical")
    pg.get_by_role("button", name=re.compile("Configurar")).first.wait_for(timeout=30_000)
    for nome, rota in [("17-tv", "/tv"), ("18-portal", "/portal"), ("19-desafio", "/desafio"), ("20-rotular", "/rotular")]:
        try:
            pg.goto(servidor.base + rota)
            pg.wait_for_timeout(2500)
            _foto(pg, pasta, nome)
            feitas.append(nome)
        except Exception as exc:  # noqa: BLE001
            print(f"  {nome}: {exc}")
    ctx.close()

    # Página do celular (sem login).
    ctx = contexto()
    pg = ctx.new_page()
    pg.goto(servidor.base + "/cam?t=exemplo")
    _foto(pg, pasta, "12-celular-cam")
    feitas.append("12-celular-cam")
    ctx.close()
    return feitas


def main() -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="", help="ex.: 1366x768-claro")
    args = ap.parse_args()
    servidor = ServidorE2E()
    try:
        servidor.subir()
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            for nome_tam, (w, h) in TAMANHOS.items():
                for nome_tema, tema in TEMAS.items():
                    chave = f"{nome_tam}-{nome_tema}"
                    if args.so and args.so != chave:
                        continue
                    feitas = capturar(servidor, navegador, DESTINO / chave, w, h, tema)
                    print(f"{chave}: {len(feitas)} capturas em {DESTINO / chave}")
            navegador.close()
    finally:
        servidor.parar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
