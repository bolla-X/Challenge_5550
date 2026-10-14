"""Capturas de todas as telas e estados, nos dois temas e em três tamanhos.

    python e2e/capturas_de_tela.py                       # bench/runtime/capturas/<rodada>/
    python e2e/capturas_de_tela.py --rodada r2 --so 390x844-escuro
    python e2e/capturas_de_tela.py --folhas              # + uma folha de contato por tela
    python e2e/capturas_de_tela.py --e2e                 # servidor do E2E em vez da demo

Por padrão sobe a DEMO (`run.py --demo`, sem webcam: `DEMO_WEBCAM=0`), que é o
que a banca vê: câmeras calibradas na planta, zona, portal, metas e missões.
As senhas que a demo imprime ficam só na memória deste processo. Com `--e2e`,
sobe o servidor do E2E (fixtures, 4 câmeras). As imagens ficam fora do git
(`bench/runtime/` é ignorado); a galeria versionada sai delas por
`scripts/galeria.py`.

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
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import PY, ServidorE2E, _porta_livre, entrar  # noqa: E402

DESTINO = RAIZ / "bench" / "runtime" / "capturas"
TAMANHOS = {"1920x1080": (1920, 1080), "1366x768": (1366, 768), "390x844": (390, 844)}
TEMAS = {"claro": "light", "escuro": "dark"}


class ServidorDemo:
    """`run.py --demo` numa porta livre; a mesma interface do ServidorE2E que este script usa."""

    foco, portal = "Pátio", "Canteiro"

    def __init__(self) -> None:
        self.porta = _porta_livre()
        self.base = f"http://127.0.0.1:{self.porta}"
        self.emails = {"supervisor": "supervisor@demo.local", "technical": "tecnico@demo.local", "operator": "operador@demo.local"}
        self.senhas: dict[str, str] = {}
        self.cameras: dict[str, int] = {}
        self.proc: subprocess.Popen | None = None
        self.log = RAIZ / "bench" / "runtime" / "capturas-demo.log"

    def subir(self, aquecer_s: float) -> None:
        env = os.environ.copy() | {"PORT": str(self.porta), "HOST": "127.0.0.1", "DEMO_WEBCAM": "0", "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen([PY, "run.py", "--demo"], cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        papel_do_email = {v: k for k, v in self.emails.items()}
        pronto = threading.Event()

        def ler() -> None:
            with self.log.open("w", encoding="utf-8") as log:
                for linha in self.proc.stdout:
                    m = re.match(r"\[demo\]\s+(\S+@demo\.local)\s+(\S+)", linha)
                    if m:  # senha: só na memória, nunca no log
                        self.senhas[papel_do_email[m.group(1)]] = m.group(2)
                        log.write(f"[demo] {m.group(1)} <senha omitida>\n")
                        continue
                    log.write(linha)
                    log.flush()
                    if "Senhas valem" in linha:
                        pronto.set()

        threading.Thread(target=ler, daemon=True).start()
        if not pronto.wait(300):
            raise RuntimeError(f"a demo não subiu em 300 s; ver {self.log}")
        limite = time.monotonic() + 300
        while time.monotonic() < limite:
            try:
                if requests.get(self.base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        s = self.sessao("technical")
        corpo = s.get(self.base + "/api/cameras", timeout=10).json()
        lista = corpo if isinstance(corpo, list) else corpo.get("items") or corpo.get("cameras") or []
        self.cameras = {c["name"]: c["id"] for c in lista}
        print(f"[capturas] demo no ar; {int(aquecer_s)} s para acumular dados reais", flush=True)
        time.sleep(aquecer_s)

    def sessao(self, papel: str) -> requests.Session:
        s = requests.Session()
        s.post(self.base + "/api/auth/login", json={"email": self.emails[papel], "password": self.senhas[papel]},
               timeout=10).raise_for_status()
        return s

    def parar(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


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


def capturar(servidor, navegador, pasta: Path, largura: int, altura: int, tema: str) -> list[str]:
    pasta.mkdir(parents=True, exist_ok=True)
    feitas: list[str] = []
    celular = largura < 768
    base = servidor.base
    nome_foco = getattr(servidor, "foco", "Multidão")
    nome_portal = getattr(servidor, "portal", "Canteiro")
    multidao, canteiro = servidor.cameras[nome_foco], servidor.cameras[nome_portal]

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
    ctx.close()

    # Técnico: foco na multidão (alerta crítico), as abas e o Raio-X.
    ctx, pg = logado("technical")

    def foco():
        pg.get_by_role("button", name=f"Configurar {nome_foco}").click(timeout=30_000)
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
    _tentar("06-escala", lambda: (pg.get_by_role("button", name="Prova de escala").first.click(timeout=20_000),
                                  _foto(pg, pasta, "06-prova-de-escala", feitas)))
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
    # Sem interceptar rota no Playwright (handler em voo derrubava a rodada):
    # o `fetch` da própria página atrasa ("carregando") ou devolve o dado de
    # teste ("vazio", "degradado"). Cada estado num
    # contexto próprio.
    def forcado(nome: str, script: str | None, rota: str, preparar=None, espera_ms: int = 2500, depois=None) -> None:
        ctx, pg = logado("technical")
        try:
            if script:
                pg.add_init_script(script)
            if preparar:
                preparar(ctx, pg)
            pg.goto(base + rota, wait_until="commit")
            if depois:
                depois(pg)
            _foto(pg, pasta, nome, feitas, espera_ms)
        finally:
            ctx.close()

    def troca_fetch(trecho: str, corpo_js: str) -> str:
        return ("(() => { const original = window.fetch; window.fetch = async (...a) => {"
                " const r = await original(...a); const u = String(a[0] && a[0].url ? a[0].url : a[0]);"
                f" if (!u.includes({json.dumps(trecho)})) return r;"
                f" const j = await r.clone().json(); const novo = ({corpo_js})(j);"
                " return new Response(JSON.stringify(novo), { status: 200, headers: { 'Content-Type': 'application/json' } }); }; })();")

    # A API da Liga demora 15 s dentro da página (o resto do app carrega normal).
    atraso = ("(() => { const original = window.fetch; window.fetch = (...a) => {"
              " const u = String(a[0] && a[0].url ? a[0].url : a[0]);"
              " return u.includes('/api/liga')"
              " ? new Promise((ok) => setTimeout(() => ok(original(...a)), 15000)) : original(...a); }; })();")
    _tentar("carregando", lambda: forcado("26-forcado-carregando-liga", atraso, "/liga", None, 2500))
    vazia = troca_fetch("/api/custodia", "(j) => ({ ...j, items: [], total: 0 })")
    _tentar("vazio", lambda: forcado("27-forcado-vazio-auditoria", vazia, "/auditoria"))
    degradar = ("(j) => ({ ...j, adaptativo: { degradado: true, reducoes: "
                "['análise a cada 3 quadros', 'inferência em 480 px'] } })")
    _tentar("degradado", lambda: forcado("28-forcado-degradado", troca_fetch(f"/api/cameras/{canteiro}/status", degradar),
                                         "/", None, 3000,
                                         lambda pg: pg.get_by_role("button", name=f"Configurar {nome_portal}").click(timeout=30_000)))

    # Sem sinal (REAL): uma câmera de rede cuja fonte não responde.
    tecnico = servidor.sessao("technical")
    fonte_rede = getattr(servidor, "fonte_rede", None)
    cid = None
    if fonte_rede is not None:
        fonte_rede.parar()
        nome = "Rede"
    else:
        nome = "Doca"
        cid = tecnico.post(base + "/api/cameras", json={"name": nome, "location": "Expedição", "source_type": "RTSP",
                                                        "source": f"rtsp://127.0.0.1:{_porta_livre()}/sem-sinal",
                                                        "fps": 12, "width": 960, "height": 540}, timeout=10).json()["id"]
        tecnico.post(f"{base}/api/cameras/{cid}/start", timeout=60)
    try:
        ctx, pg = logado("technical")
        _tentar("29-sem-sinal", lambda: (pg.get_by_role("button", name=f"Configurar {nome}").click(timeout=30_000),
                                         _foto(pg, pasta, "29-sem-sinal", feitas, 9000)))
        ctx.close()
    finally:
        if fonte_rede is not None:
            fonte_rede.iniciar()
        else:
            tecnico.post(f"{base}/api/cameras/{cid}/stop", timeout=30)
            tecnico.delete(f"{base}/api/cameras/{cid}", timeout=30)
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
    ap.add_argument("--e2e", action="store_true", help="servidor do E2E em vez da demo")
    ap.add_argument("--aquecer", type=float, default=180.0, help="segundos de demo no ar antes de capturar")
    args = ap.parse_args()
    rodada = DESTINO / args.rodada
    servidor = ServidorE2E() if args.e2e else ServidorDemo()
    try:
        if args.e2e:
            servidor.subir()
        else:
            servidor.subir(args.aquecer)
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
