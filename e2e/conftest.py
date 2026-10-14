"""E2E com o servidor REAL, Playwright (Chromium headless) e fixtures.

    python -m pytest e2e -q            # fora da suíte unitária (testpaths=tests)

O servidor sobe como em produção (`run.py`), com banco isolado em
`bench/runtime/e2e.db`, sem ler o `.env` de quem roda (VISIONEPI_DOTENV=0),
e três câmeras:

1. "Multidão" — fixture com várias pessoas sem EPI (gera alerta);
2. "Canteiro" — fixture com capacete e colete;
3. "Rede" — fonte MJPEG por HTTP (`e2e/fonte_mjpeg.py`) que o teste derruba.

Senhas são geradas a cada execução e nunca impressas.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fonte_mjpeg import FonteMJPEG  # noqa: E402

PY = sys.executable


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServidorE2E:
    def __init__(self) -> None:
        import fetch_fixtures

        self.porta = _porta_livre()
        self.base = f"http://127.0.0.1:{self.porta}"
        runtime = RAIZ / "bench" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        banco = runtime / "e2e.db"
        for sufixo in ("", "-journal", "-wal", "-shm"):  # WAL: os arquivos auxiliares velhos corromperiam o banco novo
            Path(str(banco) + sufixo).unlink(missing_ok=True)
        self.fixtures = {n: fetch_fixtures.caminho_da_fixture(n) for n in ("bench", "multidao", "queda")}
        self.fonte_rede = FonteMJPEG(self.fixtures["bench"], _porta_livre())
        self.senhas = {papel: secrets.token_urlsafe(16) for papel in ("supervisor", "technical", "operator")}
        self.emails = {papel: f"{papel}@e2e.local" for papel in self.senhas}
        self.env = os.environ.copy() | {
            "VISIONEPI_DOTENV": "0",
            "HOST": "127.0.0.1",
            "PORT": str(self.porta),
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_URL": f"sqlite:///{banco.as_posix()}",
            "AUTH_REQUIRED": "true",
            "AUTO_CREATE_TABLES": "true",
            "LLM_ENABLED": "false",
            "PPE_MODEL_PATH": "models/vyra_ppe.pt",
            "YOLO_CLASSES": "0,1,2,3,5,11,12,13",
            # Histerese menor que a de produção (8): o E2E verifica que o alerta
            # CHEGA, não o tempo de confirmação — e numa CPU carregada 8
            # inferências podem levar mais que o timeout do teste.
            "ALERT_CREATE_AFTER_FRAMES": "3",
            "RTSP_FIXTURE_FALLBACK": "",
            "SNAPSHOT_DIR": "bench/runtime/e2e-snapshots",
            # Sem limpeza a cada câmera ligada: apagaria evidência da cadeia de custódia (X3).
            "CLEANUP_ON_MONITOR_START": "false",
            "PYTHONUNBUFFERED": "1",
        }
        self.log = runtime / "e2e.log"
        self.proc: subprocess.Popen | None = None
        self.cameras: dict[str, int] = {}

    def flask(self, *args: str) -> None:
        subprocess.run([PY, "-m", "flask", "--app", "wsgi", *args], cwd=RAIZ, env=self.env, check=True,
                       capture_output=True)

    def subir(self) -> None:
        self.fonte_rede.iniciar()
        # Banco e usuários ANTES do servidor (create_all roda no create_app).
        for papel in ("supervisor", "technical"):
            self.flask("users", "create", "--email", self.emails[papel], "--name", papel.title(), "--role", papel,
                       "--password", self.senhas[papel])
        self.proc = subprocess.Popen([PY, "run.py"], cwd=RAIZ, env=self.env, stdout=self.log.open("w", encoding="utf-8"),
                                     stderr=subprocess.STDOUT)
        limite = time.monotonic() + 120
        while time.monotonic() < limite:
            if self.proc.poll() is not None:
                raise RuntimeError(f"servidor morreu; ver {self.log}")
            try:
                if requests.get(self.base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    break
            except requests.RequestException:
                time.sleep(0.3)
        tecnico = self.sessao("technical")
        for nome, tipo, fonte in (("Multidão", "Arquivo", str(self.fixtures["multidao"])),
                                  ("Canteiro", "Arquivo", str(self.fixtures["bench"])),
                                  ("Rede", "RTSP", self.fonte_rede.url),
                                  ("Queda", "Arquivo", str(self.fixtures["queda"]))):
            r = tecnico.post(self.base + "/api/cameras", json={"name": nome, "source_type": tipo, "source": fonte,
                                                                "fps": 12, "width": 960, "height": 540}, timeout=10)
            r.raise_for_status()
            self.cameras[nome] = r.json()["id"]
        # O operador nasce vinculado à câmera 1 (Multidão).
        self.flask("users", "create", "--email", self.emails["operator"], "--name", "Operador", "--role", "operator",
                   "--camera-id", str(self.cameras["Multidão"]), "--password", self.senhas["operator"])
        for cid in self.cameras.values():
            tecnico.post(f"{self.base}/api/cameras/{cid}/start", timeout=60).raise_for_status()

    def sessao(self, papel: str) -> requests.Session:
        s = requests.Session()
        s.post(self.base + "/api/auth/login", json={"email": self.emails[papel], "password": self.senhas[papel]},
               timeout=10).raise_for_status()
        return s

    def parar(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.fonte_rede.parar()


@pytest.fixture(scope="session")
def servidor():
    srv = ServidorE2E()
    try:
        srv.subir()
        yield srv
    finally:
        srv.parar()


@pytest.fixture(scope="session")
def playwright_sessao():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def navegador(playwright_sessao):
    # Câmera falsa do Chromium para o F6 (celular como câmera): o
    # getUserMedia recebe um vídeo sintético e a permissão é concedida
    # sem diálogo. Não afeta os outros testes.
    nav = playwright_sessao.chromium.launch(
        headless=True, args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
    )
    yield nav
    nav.close()


@pytest.fixture(scope="session")
def navegador_gpu(playwright_sessao):
    """Chromium com a GPU da máquina (o "perfil normal" de um navegador de verdade).

    O headless padrão desenha WebGL no SwiftShader (software): serve para
    provar que funciona, não para medir tempo de quadro. Ver CHANGELOG (X1).
    """
    nav = playwright_sessao.chromium.launch(headless=True, args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
    yield nav
    nav.close()


@pytest.fixture()
def pagina(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1366, "height": 768})
    pagina = contexto.new_page()
    pagina.erros_console = []
    pagina.on("console", lambda m: pagina.erros_console.append(m.text) if m.type == "error" else None)
    yield pagina
    contexto.close()


def entrar(pagina, servidor, papel: str) -> None:
    pagina.goto(servidor.base + "/")
    # 60 s: com 4 câmeras e alertas acumulados, o primeiro carregamento depois
    # de limpar os cookies já passou de 30 s numa rodada completa.
    pagina.get_by_label("E-mail").wait_for(timeout=60_000)
    pagina.get_by_label("E-mail").fill(servidor.emails[papel])
    pagina.get_by_label("Senha").fill(servidor.senhas[papel])
    pagina.get_by_role("button", name="Entrar").click()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Teste que falha deixa a tela e o texto da página em bench/runtime/e2e-falhas/.

    Sem isto, falha por tempo esgotado só diz "não apareceu" — e não mostra o
    que estava na tela no lugar.
    """
    resultado = yield
    relatorio = resultado.get_result()
    pagina = item.funcargs.get("pagina") if hasattr(item, "funcargs") else None
    if relatorio.when != "call" or not relatorio.failed or pagina is None:
        return
    pasta = RAIZ / "bench" / "runtime" / "e2e-falhas"
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        pagina.screenshot(path=str(pasta / f"{item.name}.png"))
        (pasta / f"{item.name}.txt").write_text(
            f"url: {pagina.url}\nerros de console: {getattr(pagina, 'erros_console', [])}\n\n" + pagina.inner_text("body")[:5000],
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001  (diagnóstico nunca derruba o relatório)
        pass
