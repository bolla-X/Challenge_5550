"""Quantos itens o painel de alertas mostra numa gravação, antes e depois dos incidentes (P0.2).

    python scripts/contar_incidentes.py --fixture multidao --segundos 150 --rotulo depois
    python scripts/contar_incidentes.py --raiz <worktree do pre-missao-2> --fixture multidao --rotulo antes

Sobe o servidor REAL (`run.py`) da árvore `--raiz` com banco novo, cadastra UMA
câmera com a gravação e TODOS os EPIs ligados (o padrão de câmera nova), deixa
rodar `--segundos` com alguém olhando (o `video_feed` aberto: a gravação anda
em tempo real, como na demo) e conta:

- alertas criados (cada um era uma linha/pílula no painel antigo);
- incidentes criados (o que o painel novo mostra), se a árvore tiver a tabela;
- o máximo de itens ativos AO MESMO TEMPO no painel, lido do `/status` a cada
  segundo — e, no novo, o máximo de incidentes ativos com a mesma (regra, zona).

A gravação toca em tempo de relógio e a inferência depende da carga da
máquina: duas rodadas não veem exatamente os mesmos quadros. O número é o da
rodada, com a carga de fundo registrada; não é uma constante da gravação.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _carga_de_fundo() -> float | None:
    try:
        import psutil

        return round(psutil.cpu_percent(interval=1.0), 1)
    except Exception:  # noqa: BLE001
        return None


def medir(raiz: Path, fixture: Path, segundos: float, rotulo: str) -> dict:
    py = sys.executable
    porta = _porta_livre()
    base = f"http://127.0.0.1:{porta}"
    runtime = RAIZ / "bench" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    banco = runtime / f"incidentes-{rotulo}.db"
    for sufixo in ("", "-journal", "-wal", "-shm"):  # WAL: os arquivos auxiliares velhos corromperiam o banco novo
        Path(str(banco) + sufixo).unlink(missing_ok=True)
    senha = secrets.token_urlsafe(16)
    env = os.environ.copy() | {
        "VISIONEPI_DOTENV": "0",
        "HOST": "127.0.0.1",
        "PORT": str(porta),
        "SECRET_KEY": secrets.token_hex(32),
        "DATABASE_URL": f"sqlite:///{banco.as_posix()}",
        "AUTH_REQUIRED": "true",
        "AUTO_CREATE_TABLES": "true",
        "LLM_ENABLED": "false",
        "PPE_MODEL_PATH": "models/vyra_ppe.pt",
        "YOLO_CLASSES": "0,1,2,3,5,11,12,13",
        "RTSP_FIXTURE_FALLBACK": "",
        "SNAPSHOT_DIR": f"bench/runtime/incidentes-{rotulo}-snapshots",
        "CLEANUP_DIRECTORIES": f"bench/runtime/incidentes-{rotulo}-snapshots",
        "PYTHONUNBUFFERED": "1",
    }
    subprocess.run([py, "-m", "flask", "--app", "wsgi", "users", "create", "--email", "tec@medir.local", "--name", "Tec",
                    "--role", "technical", "--password", senha], cwd=raiz, env=env, check=True, capture_output=True)
    log = (runtime / f"incidentes-{rotulo}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([py, "run.py"], cwd=raiz, env=env, stdout=log, stderr=subprocess.STDOUT)
    parar_video = threading.Event()
    try:
        limite = time.monotonic() + 180
        while time.monotonic() < limite:
            if proc.poll() is not None:
                raise RuntimeError("servidor morreu; ver o log em bench/runtime")
            try:
                if requests.get(base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        s = requests.Session()
        s.post(base + "/api/auth/login", json={"email": "tec@medir.local", "password": senha}, timeout=10).raise_for_status()
        r = s.post(base + "/api/cameras", json={"name": "Medição", "source_type": "Arquivo", "source": str(fixture),
                                               "fps": 12, "width": 960, "height": 540}, timeout=10)
        r.raise_for_status()
        cid = r.json()["id"]
        s.post(f"{base}/api/cameras/{cid}/start", timeout=120).raise_for_status()

        # Alguém olhando: o MJPEG aberto faz a gravação andar em tempo real.
        def assistir() -> None:
            try:
                with s.get(f"{base}/api/cameras/{cid}/video_feed", stream=True, timeout=30) as resp:
                    for _ in resp.iter_content(65536):
                        if parar_video.is_set():
                            break
            except requests.RequestException:
                pass

        threading.Thread(target=assistir, daemon=True).start()
        carga = _carga_de_fundo()
        max_alertas = max_incidentes = max_mesma_chave = 0
        max_alertas_mesma_regra = 0
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            st = s.get(f"{base}/api/cameras/{cid}/status", timeout=10).json()
            alertas = st.get("active_alerts") or []
            max_alertas = max(max_alertas, len(alertas))
            if alertas:
                max_alertas_mesma_regra = max(max_alertas_mesma_regra, max(Counter(a["rule"] for a in alertas).values()))
            incs = st.get("active_incidents")
            if incs is not None:
                max_incidentes = max(max_incidentes, len(incs))
                if incs:
                    max_mesma_chave = max(max_mesma_chave, max(Counter((i["rule"], i["zona"]) for i in incs).values()))
            time.sleep(1.0)
        analises = s.get(f"{base}/api/diagnostics/pipeline?janela_s=600", timeout=10).json()
        totais = ((analises.get("cameras") or {}).get(str(cid)) or {}).get("stats", {}).get("totais", {})
    finally:
        parar_video.set()
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    with sqlite3.connect(banco) as c:
        alertas_criados = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        por_regra = dict(c.execute("SELECT rule, COUNT(*) FROM alerts GROUP BY rule").fetchall())
        pessoas = c.execute("SELECT COUNT(DISTINCT json_extract(metadata_json, '$.person_id')) FROM alerts").fetchone()[0]
        tem_incidentes = bool(c.execute("SELECT name FROM sqlite_master WHERE name='incidentes'").fetchone())
        incidentes_criados = c.execute("SELECT COUNT(*) FROM incidentes").fetchone()[0] if tem_incidentes else None
    return {
        "rotulo": rotulo,
        "raiz": str(raiz),
        "fixture": fixture.name,
        "segundos": segundos,
        "carga_de_fundo_pct": carga,
        "inferencias": totais.get("inferencias"),
        "alertas_criados": alertas_criados,
        "alertas_por_regra": por_regra,
        "ids_de_pessoa_com_alerta": pessoas,
        "incidentes_criados": incidentes_criados,
        "max_itens_no_painel_antigo": max_alertas,
        "max_alertas_ativos_mesma_regra": max_alertas_mesma_regra,
        "max_incidentes_ativos": max_incidentes if tem_incidentes else None,
        "max_incidentes_mesma_regra_e_zona": max_mesma_chave if tem_incidentes else None,
    }


def main() -> None:
    import fetch_fixtures

    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--fixture", default="multidao")
    ap.add_argument("--segundos", type=float, default=150)
    ap.add_argument("--rotulo", default="depois")
    a = ap.parse_args()
    resultado = medir(Path(a.raiz), fetch_fixtures.caminho_da_fixture(a.fixture), a.segundos, f"{a.rotulo}-{a.fixture}")
    destino = RAIZ / "bench" / "results" / f"incidentes-{a.rotulo}-{a.fixture}-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
