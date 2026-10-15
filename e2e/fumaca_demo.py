"""Fumaça da demo de QUALQUER checkout: sobe `run.py --demo` lá e confere o essencial.

    python e2e/fumaca_demo.py --raiz C:/caminho/do/clone [--python C:/caminho/do/clone/.venv/Scripts/python.exe]

Usado no teste de clone limpo (Fase D da MISSÃO 2): o clone segue o README à
risca e este script, rodando com o Playwright DESTE checkout, verifica contra
o servidor do clone:

1. a demo sobe e imprime as contas (senhas só na memória, nunca no log);
2. login do supervisor;
3. as câmeras da demo estão rodando e publicam análise (`analises_publicadas`);
4. o vídeo de uma câmera chega ao canvas da tela de foco;
5. o palco abre e a cena do Portal mostra o veredito e as câmeras pausadas.

Sai com 0 se tudo passou; imprime cada verificação.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import _porta_livre, encerrar_arvore, entrar  # noqa: E402


class DemoEm:
    """`run.py --demo` numa pasta qualquer, com o Python dela."""

    def __init__(self, raiz: Path, python: Path) -> None:
        self.raiz, self.python = raiz, python
        self.porta = _porta_livre()
        self.base = f"http://127.0.0.1:{self.porta}"
        self.emails = {"supervisor": "supervisor@demo.local", "technical": "tecnico@demo.local",
                       "operator": "operador@demo.local"}
        self.senhas: dict[str, str] = {}
        self.proc: subprocess.Popen | None = None
        self.log = Path(__file__).resolve().parent.parent / "bench" / "runtime" / f"fumaca-{raiz.name}.log"

    def subir(self, limite_s: float = 600.0) -> float:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy() | {"PORT": str(self.porta), "HOST": "127.0.0.1", "DEMO_WEBCAM": "0", "PYTHONUNBUFFERED": "1"}
        env.pop("VIRTUAL_ENV", None)
        inicio = time.monotonic()
        self.proc = subprocess.Popen([str(self.python), "run.py", "--demo"], cwd=self.raiz, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        papel = {v: k for k, v in self.emails.items()}
        pronto = threading.Event()

        def ler() -> None:
            with self.log.open("w", encoding="utf-8") as log:
                for linha in self.proc.stdout:
                    m = re.match(r"\[demo\]\s+(\S+@demo\.local)\s+(\S+)", linha)
                    if m:
                        self.senhas[papel[m.group(1)]] = m.group(2)
                        log.write(f"[demo] {m.group(1)} <senha omitida>\n")
                        continue
                    log.write(linha)
                    log.flush()
                    if "Senhas valem" in linha:
                        pronto.set()

        threading.Thread(target=ler, daemon=True).start()
        if not pronto.wait(limite_s):
            raise RuntimeError(f"a demo não subiu em {limite_s:.0f} s; ver {self.log}")
        # As contas saem antes de o servidor HTTP aceitar conexão (o aquecimento
        # dos modelos vem no meio; com a CPU tomada por outros programas passou de 120 s).
        fim = inicio + limite_s
        while time.monotonic() < fim:
            try:
                if requests.get(self.base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    return time.monotonic() - inicio
            except requests.RequestException:
                time.sleep(0.5)
        raise RuntimeError(f"a demo imprimiu as contas mas não respondeu HTTP; ver {self.log}")

    def sessao(self, papel: str) -> requests.Session:
        s = requests.Session()
        s.post(self.base + "/api/auth/login", json={"email": self.emails[papel], "password": self.senhas[papel]},
               timeout=10).raise_for_status()
        return s

    def parar(self) -> None:
        encerrar_arvore(self.proc, 15.0)


def verificar(demo: DemoEm) -> list[tuple[str, bool, str]]:
    from playwright.sync_api import sync_playwright

    resultados: list[tuple[str, bool, str]] = []

    def marca(nome: str, ok: bool, detalhe: str = "") -> None:
        resultados.append((nome, ok, detalhe))
        print(f"[fumaça] {'OK ' if ok else 'FALHOU'} {nome} {detalhe}", flush=True)

    sessao = demo.sessao("supervisor")
    marca("login do supervisor pela API", True)
    corpo = sessao.get(demo.base + "/api/cameras", timeout=10).json()
    cameras = corpo if isinstance(corpo, list) else corpo.get("items") or corpo.get("cameras") or []
    nomes = {c["name"]: c["id"] for c in cameras}
    marca("câmeras da demo cadastradas", len(nomes) >= 4, str(sorted(nomes)))
    limite = time.monotonic() + 180
    analisando: set[str] = set()
    while time.monotonic() < limite and len(analisando) < len(nomes):
        diag = sessao.get(demo.base + "/api/diagnostics/pipeline", timeout=10).json().get("cameras") or {}
        for nome, cid in nomes.items():
            if (((diag.get(str(cid)) or {}).get("stats") or {}).get("totais") or {}).get("analises_publicadas"):
                analisando.add(nome)
        time.sleep(2)
    marca("todas as câmeras publicam análise", analisando == set(nomes), str(sorted(analisando)))

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        try:
            pagina = navegador.new_context(viewport={"width": 1920, "height": 1080}).new_page()
            entrar(pagina, demo, "supervisor")
            pagina.get_by_role("button", name=re.compile(r"^Câmeras")).first.click(timeout=60_000)
            pagina.get_by_role("button", name=re.compile("Configurar Pátio")).click(timeout=30_000)
            video = pagina.locator("canvas.live-video").first
            video.wait_for(timeout=30_000)
            fim = time.monotonic() + 60
            quadros = 0
            while time.monotonic() < fim and quadros < 10:
                quadros = int(video.get_attribute("data-frames") or 0)
                time.sleep(0.5)
            marca("vídeo chega ao canvas", quadros >= 10, f"{quadros} quadros")
            pagina.goto(demo.base + "/palco")
            pagina.locator("[data-testid=palco]").wait_for(timeout=30_000)
            for _ in range(15):
                pagina.keyboard.press("ArrowLeft")
            pagina.wait_for_function("document.querySelector('[data-testid=palco]')?.dataset.cena === '0'", timeout=15_000)
            pagina.keyboard.press("ArrowRight")
            pagina.locator("[data-testid=palco][data-chave=portal] [data-testid=portal]").wait_for(timeout=30_000)
            pausadas = pagina.locator("[data-testid=palco-pausadas]")
            pausadas.wait_for(timeout=15_000)
            marca("palco: cena do Portal pausa as outras", "pela apresentação" in pausadas.inner_text(), pausadas.inner_text())
            try:
                pagina.wait_for_function(
                    "document.querySelector('[data-testid=portal]')?.dataset.veredito === 'approved'", timeout=60_000
                )
                marca("palco: Portal chega a Liberado", True)
            except Exception as exc:  # noqa: BLE001
                marca("palco: Portal chega a Liberado", False, type(exc).__name__)
            pagina.keyboard.press("ArrowLeft")
        finally:
            navegador.close()
    return resultados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", required=True, type=Path)
    ap.add_argument("--python", type=Path, default=None, help="padrão: <raiz>/.venv/Scripts/python.exe")
    args = ap.parse_args()
    raiz = args.raiz.resolve()
    python = args.python or (raiz / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    demo = DemoEm(raiz, python)
    try:
        subida = demo.subir()
        print(f"[fumaça] OK  demo no ar em {subida:.0f} s (até imprimir as contas)", flush=True)
        resultados = verificar(demo)
    finally:
        demo.parar()
    falhas = [nome for nome, ok, _ in resultados if not ok]
    print(f"[fumaça] {len(resultados) - len(falhas)}/{len(resultados)} verificações passaram", flush=True)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
