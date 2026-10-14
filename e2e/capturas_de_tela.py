"""Capturas de todas as telas e estados, nos dois temas e em três tamanhos.

    python e2e/capturas_de_tela.py                       # bench/runtime/capturas/<rodada>/
    python e2e/capturas_de_tela.py --rodada r2 --so 390x844-escuro
    python e2e/capturas_de_tela.py --folhas              # + uma folha de contato por tela

Sobe o MESMO servidor do E2E (fixtures, 3 papéis, senhas geradas e nunca
impressas, 4 câmeras ligadas) e percorre as telas como cada papel. As imagens
ficam fora do git (`bench/runtime/` é ignorado); a galeria versionada sai
delas por `scripts/galeria.py`.

Serve ao ciclo de revisão visual da MISSÃO 2 (Fase C, item 7): rotas e
estados importantes (vazio, carregando, alerta crítico, degradado, sem sinal)
em 1920×1080, 1366×768 e 390×844, claro e escuro. Os estados "vazio",
"carregando" e "degradado" são FORÇADOS no navegador (resposta da API trocada
ou atrasada) e o nome do arquivo diz isso: são a tela real com dado de teste,
não dado do sistema.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import ServidorE2E, entrar  # noqa: E402

DESTINO = RAIZ / "bench" / "runtime" / "capturas"
TAMANHOS = {"1920x1080": (1920, 1080), "1366x768": (1366, 768), "390x844": (390, 844)}
TEMAS = {"claro": "light", "escuro": "dark"}


def _foto(pagina, pasta: Path, nome: str, feitas: list[str], espera_ms: int = 1500) -> None:
    pagina.wait_for_timeout(espera_ms)  # animações curtas e o primeiro quadro do vídeo
    pagina.screenshot(path=str(pasta / f"{nome}.png"), full_page=False)
    feitas.append(nome)


def _tentar(nome: str, acao) -> None:
    try:
        acao()
    except Exception as exc:  # noqa: BLE001  (inventário visual: registra e segue)
        print(f"  {nome}: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}")


def _abrir_aba(pagina, rotulo: str) -> None:
    aba = pagina.get_by_role("tab", name=rotulo)
    if aba.count():
        aba.click()
        return
    pagina.locator(".tabs-more > button").click()
    pagina.get_by_role("menuitem", name=rotulo).click()


def capturar(servidor: ServidorE2E, navegador, pasta: Path, largura: int, altura: int, tema: str) -> list[str]:
    pasta.mkdir(parents=True, exist_ok=True)
    feitas: list[str] = []
    celular = largura < 768
    base = servidor.base
    multidao, canteiro = servidor.cameras["Multidão"], servidor.cameras["Canteiro"]

    def contexto():
        extra = {"is_mobile": True, "has_touch": True, "device_scale_factor": 2} if celular else {}
        ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=tema, **extra)
        ctx.add_init_script(f"try {{ localStorage.setItem('visionepi-theme', '{tema}'); }} catch (e) {{}}")
        return ctx

    def logado(papel: str):
        ctx = contexto()
        pg = ctx.new_page()
        entrar(pg, servidor, papel)
        pg.wait_for_timeout(3000)
        return ctx, pg

    # Sem login.
    ctx = contexto()
    pg = ctx.new_page()
    pg.goto(base + "/")
    _foto(pg, pasta, "01-login", feitas)
    ctx.close()

    # Supervisor: início, câmeras, contas, sobre, prova de escala.
    ctx, pg = logado("supervisor")
    _foto(pg, pasta, "02-supervisor-inicio", feitas)
    _tentar("03-cameras", lambda: (pg.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=20_000),
                                   _foto(pg, pasta, "03-cameras-grade", feitas, 3000)))
    _tentar("04-contas", lambda: (pg.goto(base + "/"), pg.get_by_role("button", name="Contas").first.click(timeout=20_000),
                                  _foto(pg, pasta, "04-supervisor-contas", feitas)))
    _tentar("05-sobre", lambda: (pg.goto(base + "/"), pg.get_by_role("button", name="Sobre", exact=True).first.click(timeout=20_000),
                                 _foto(pg, pasta, "05-sobre", feitas)))
    _tentar("06-escala", lambda: (pg.goto(base + "/"), pg.get_by_role("button", name="Prova de escala").first.click(timeout=20_000),
                                  _foto(pg, pasta, "06-prova-de-escala", feitas)))
    ctx.close()

    # Técnico: foco na multidão (alerta crítico), as abas e o Raio-X.
    ctx, pg = logado("technical")

    def foco():
        pg.get_by_role("button", name="Configurar Multidão").click(timeout=30_000)
        pg.locator("canvas.live-video").first.wait_for(timeout=30_000)
        pg.locator("[data-testid=pilula-incidente], .over-pill.alert").first.wait_for(timeout=90_000)
        _foto(pg, pasta, "07-foco-alerta-critico", feitas, 2500)
        for i, aba in enumerate(["Alertas", "Pessoas", "Diagnóstico", "Mapa de calor", "Quedas e postura"], start=1):
            _tentar(f"aba {aba}", lambda aba=aba, i=i: (_abrir_aba(pg, aba), _foto(
                pg, pasta, f"08-foco-aba-{i}-{re.sub(r'[^a-z]+', '-', aba.lower()).strip('-')}", feitas)))
        pg.keyboard.press("x")
        _foto(pg, pasta, "09-foco-raio-x", feitas, 2500)
        pg.keyboard.press("x")

    _tentar("foco", foco)
    ctx.close()

    # Telas de tela cheia (técnico).
    ctx, pg = logado("technical")
    rotas = [
        ("10-gemeo-3d", "/gemeo", 4000), ("11-gemeo-2d", "/gemeo?2d=1", 2500),
        ("12-simulador", f"/simulador?camera={multidao}", 3000), ("13-auditoria", "/auditoria", 2500),
        ("14-liga", "/liga", 2500), ("15-retrospectiva", "/retrospectiva", 3000), ("16-tv", "/tv", 3000),
        ("17-portal", f"/portal?camera={canteiro}", 3000), ("18-portal-enganar", f"/portal?camera={canteiro}&desafio=1", 3000),
        ("19-rotular", "/rotular", 2500), ("20-desafio", "/desafio", 2500), ("21-relatorio-turno", "/relatorio/turno", 2500),
        ("22-palco", "/palco", 3000),
    ]
    for nome, rota, espera in rotas:
        _tentar(nome, lambda nome=nome, rota=rota, espera=espera: (pg.goto(base + rota), _foto(pg, pasta, nome, feitas, espera)))
    ctx.close()

    # Operador: quiosque da câmera do setor.
    ctx, pg = logado("operator")
    _tentar("23-operador", lambda: (pg.locator("canvas.live-video").first.wait_for(timeout=30_000),
                                    _foto(pg, pasta, "23-operador-quiosque", feitas, 3000)))
    ctx.close()

    # Páginas sem login: controle do palco e celular como câmera.
    ctx = contexto()
    pg = ctx.new_page()
    _tentar("24-controle", lambda: (pg.goto(base + "/palco/controle?t=token-de-captura"), _foto(pg, pasta, "24-palco-controle", feitas)))
    _tentar("25-cam", lambda: (pg.goto(base + "/cam?t=exemplo"), _foto(pg, pasta, "25-celular-cam", feitas)))
    ctx.close()

    # Estados FORÇADOS (o nome do arquivo diz): carregando, vazio, degradado.
    ctx, pg = logado("technical")
    lentas = re.compile(r".*/api/(liga|missoes|retrospectiva).*")

    def carregando():
        pg.route(lentas, lambda rota: (time.sleep(6), rota.continue_()))
        pg.goto(base + "/liga", wait_until="commit")
        _foto(pg, pasta, "26-forcado-carregando-liga", feitas, 900)
        pg.unroute(lentas)

    def vazio():
        incidentes = re.compile(r".*/api/incidentes.*")
        pg.route(incidentes, lambda rota: rota.fulfill(status=200, content_type="application/json",
                                                       body=json.dumps({"items": [], "total": 0})))
        pg.goto(base + "/auditoria")
        _foto(pg, pasta, "27-forcado-vazio-auditoria", feitas, 2500)
        pg.unroute(incidentes)

    def degradado():
        status = re.compile(rf".*/api/cameras/{canteiro}/status.*")

        def trocar(rota):
            resposta = rota.fetch()
            corpo = resposta.json()
            corpo["adaptativo"] = {"degradado": True, "reducoes": ["análise a cada 3 quadros", "inferência em 480 px"]}
            rota.fulfill(response=resposta, body=json.dumps(corpo))

        pg.route(status, trocar)
        pg.goto(base + "/")
        pg.get_by_role("button", name="Configurar Canteiro").click(timeout=30_000)
        pg.locator("[data-testid=aviso-degradado]").first.wait_for(timeout=15_000)
        _foto(pg, pasta, "28-forcado-degradado", feitas, 2000)
        pg.unroute(status)

    _tentar("carregando", carregando)
    _tentar("vazio", vazio)
    _tentar("degradado", degradado)
    ctx.close()

    # Sem sinal (REAL): a fonte de rede cai; a câmera "Rede" mostra o estado.
    servidor.fonte_rede.parar()
    try:
        ctx, pg = logado("technical")
        _tentar("29-sem-sinal", lambda: (pg.get_by_role("button", name="Configurar Rede").click(timeout=30_000),
                                         _foto(pg, pasta, "29-sem-sinal-rede", feitas, 9000)))
        ctx.close()
    finally:
        servidor.fonte_rede.iniciar()
    return feitas


def folhas_de_contato(rodada: Path) -> None:
    """Uma imagem por tela com as 6 variações lado a lado (revisão mais rápida)."""
    from PIL import Image, ImageDraw

    variantes = [f"{t}-{m}" for t in TAMANHOS for m in TEMAS]
    nomes = sorted({p.stem for v in variantes for p in (rodada / v).glob("*.png")})
    saida = rodada / "folhas"
    saida.mkdir(exist_ok=True)
    for nome in nomes:
        quadros = []
        for v in variantes:
            arq = rodada / v / f"{nome}.png"
            if arq.exists():
                im = Image.open(arq).convert("RGB")
                im.thumbnail((960, 1000))
                quadros.append((v, im))
        if not quadros:
            continue
        largura = sum(im.width for _, im in quadros) + 10 * (len(quadros) + 1)
        altura = max(im.height for _, im in quadros) + 40
        folha = Image.new("RGB", (largura, altura), (128, 128, 128))
        x = 10
        for v, im in quadros:
            folha.paste(im, (x, 30))
            ImageDraw.Draw(folha).text((x, 8), v, fill=(255, 255, 255))
            x += im.width + 10
        folha.save(saida / f"{nome}.jpg", quality=80)


def main() -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", default="r1")
    ap.add_argument("--so", default="", help="ex.: 1366x768-claro")
    ap.add_argument("--folhas", action="store_true")
    args = ap.parse_args()
    rodada = DESTINO / args.rodada
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
                    feitas = capturar(servidor, navegador, rodada / chave, w, h, tema)
                    print(f"{chave}: {len(feitas)} capturas", flush=True)
            navegador.close()
    finally:
        servidor.parar()
    if args.folhas:
        folhas_de_contato(rodada)
    return 0


if __name__ == "__main__":
    sys.exit(main())
