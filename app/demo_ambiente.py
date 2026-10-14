"""Ambiente da demo, preparado ANTES de qualquer import do pacote `app`.

O `Config` lê as variáveis de ambiente no import; por isso este arquivo não
importa nada de `app` e o `run.py` o carrega pelo caminho (importar `app.*`
executaria o `app/__init__.py`, que importa o `Config` cedo demais).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
PASTA = BASE_DIR / "instance" / "demo"
BANCO = PASTA / "demo.db"
TOKEN = PASTA / "token"
FIXTURES = BASE_DIR / "tests" / "fixtures"

# Câmeras da demo: (nome, setor, arquivo). O setor é o que o Modo TV agrega.
GRAVACOES = [
    ("Canteiro", "Obra", "bench.mp4"),
    ("Pátio", "Expedição", "next_multidao.mp4"),
    ("Escada", "Manutenção", "next_queda.mp4"),
]
# EPIs ligados nas câmeras da demo: capacete, colete e luvas. Óculos, máscara,
# calçado e protetor auricular ficam desligados — nas gravações eles não
# aparecem de forma útil, e cada um somaria um alerta por pessoa na tela.
EPIS_DESLIGADOS_NA_DEMO = ("glasses", "mask", "safety_shoe", "ear_protection")


# Zona de risco do Pátio: faixa da direita (onde os pedestres entram).
ZONA_PATIO = [[0.62, 0.30], [0.98, 0.30], [0.98, 0.98], [0.62, 0.98]]
PLANTA_PATIO = {
    "pontos_camera": [[0.05, 0.55], [0.95, 0.55], [0.98, 0.98], [0.02, 0.98]],
    "pontos_planta": [[0.10, 0.10], [0.90, 0.10], [0.90, 0.90], [0.10, 0.90]],
}
METAS = {"Obra": {"minutos_conformes": 30, "checkins_portal": 5}, "Portaria": {"minutos_conformes": 30, "checkins_portal": 10}}


def preparar_ambiente() -> None:
    """Antes do `create_app()`: banco novo e configuração da demo no ambiente."""
    faltando = [arq for _, _, arq in GRAVACOES if not (FIXTURES / arq).exists()]
    if faltando:
        raise SystemExit(f"[demo] gravações ausentes em tests/fixtures: {', '.join(faltando)}. "
                         "Rode uma vez, com internet: python scripts/fetch_fixtures.py")
    PASTA.mkdir(parents=True, exist_ok=True)
    for arquivo in (BANCO, Path(str(BANCO) + "-journal")):
        try:
            if arquivo.exists():
                arquivo.unlink()
        except PermissionError:
            raise SystemExit("[demo] o banco da demo está em uso: já há uma demo rodando? Feche-a e tente de novo.") from None
    for sub in ("clips", "snapshots", "rotulos"):
        shutil.rmtree(PASTA / sub, ignore_errors=True)
    os.environ.update({
        "VISIONEPI_DOTENV": "0",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite:///{BANCO.as_posix()}",
        "AUTO_CREATE_TABLES": "true",
        "AUTH_REQUIRED": "true",
        "SECRET_KEY": secrets.token_hex(32),
        "LLM_ENABLED": "false",
        "REPLAY_DIR": str(PASTA / "clips"),
        "SNAPSHOT_DIR": str(PASTA / "snapshots"),
        "CLEANUP_DIRECTORIES": str(PASTA / "snapshots"),
        "ROTULOS_DIR": str(PASTA / "rotulos"),
        "RTSP_FIXTURE_FALLBACK": "",
        "DEFAULT_FEATURES": "ppe,helmet,vest,gloves,pose,falls,posture,risk_area,sos,ergonomia,imobilidade",
    })
    TOKEN.write_text(secrets.token_urlsafe(32), encoding="utf-8")


def resetar_pelo_terminal(porta: int) -> dict[str, Any]:
    """`flask demo reset`: pede ao servidor da demo; sem servidor, limpa o banco direto."""
    inicio = time.monotonic()
    if TOKEN.exists():
        pedido = urllib.request.Request(f"http://127.0.0.1:{porta}/api/demo/reset", method="POST", data=b"{}",
                                        headers={"X-Demo-Token": TOKEN.read_text(encoding="utf-8").strip(),
                                                 "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resposta:
                return json.loads(resposta.read()) | {"via": "servidor"}
        except (urllib.error.URLError, OSError):
            pass  # servidor fora do ar: segue para o banco
    if not BANCO.exists():
        raise SystemExit("[demo] não há banco da demo. Rode: python run.py --demo")
    with sqlite3.connect(BANCO) as conexao:
        conexao.execute("DELETE FROM alerts")
        conexao.execute("DELETE FROM event_logs")
    for sub in ("clips", "snapshots"):
        shutil.rmtree(PASTA / sub, ignore_errors=True)
    return {"ok": True, "segundos": round(time.monotonic() - inicio, 2), "via": "banco (servidor fora do ar)"}
