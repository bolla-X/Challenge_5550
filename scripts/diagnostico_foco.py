"""Quanto a câmera em foco recebe do agendador com as 4 gravações ligadas (P0.1).

    python scripts/diagnostico_foco.py --foco multidao --segundos 90 [--env CHAVE=VALOR ...]

Sobe o servidor real como o E2E (4 câmeras: multidão, canteiro, bench por rede
não — aqui as 3 gravações + a queda), abre o `video_feed` da câmera em foco e,
ao fim, lê do `/api/diagnostics/pipeline` as inferências servidas por câmera, a
fração da câmera em foco e quantos pré-alertas de aproximação (F3) saíram na
linha do tempo. Serve para decidir o peso do foco sem adivinhar.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    import fetch_fixtures

    ap = argparse.ArgumentParser()
    ap.add_argument("--foco", default="multidao")
    ap.add_argument("--segundos", type=float, default=90)
    ap.add_argument("--zona", action="store_true", help="zona na metade direita da câmera em foco (como o E2E do F3)")
    ap.add_argument("--portal", action="store_true", help="liga o portal (capacete+colete) na câmera em foco e mede até 'Liberado'")
    ap.add_argument("--repeticoes", type=int, default=1, help="com --portal: zera o portal e mede de novo N vezes")
    ap.add_argument("--env", action="append", default=[])
    a = ap.parse_args()
    porta = _porta_livre()
    base = f"http://127.0.0.1:{porta}"
    runtime = RAIZ / "bench" / "runtime"
    banco = runtime / "diagnostico-foco.db"
    for sufixo in ("", "-journal", "-wal", "-shm"):  # WAL: os arquivos auxiliares velhos corromperiam o banco novo
        Path(str(banco) + sufixo).unlink(missing_ok=True)
    for pasta in ("diagnostico-clips", "diagnostico-trilhas"):
        shutil.rmtree(runtime / pasta, ignore_errors=True)
    senha = secrets.token_urlsafe(16)
    env = os.environ.copy() | {
        "VISIONEPI_DOTENV": "0", "HOST": "127.0.0.1", "PORT": str(porta), "SECRET_KEY": secrets.token_hex(32),
        "DATABASE_URL": f"sqlite:///{banco.as_posix()}", "AUTH_REQUIRED": "true", "AUTO_CREATE_TABLES": "true",
        "LLM_ENABLED": "false", "PPE_MODEL_PATH": "models/vyra_ppe.pt", "YOLO_CLASSES": "0,1,2,3,5,11,12,13",
        "ALERT_CREATE_AFTER_FRAMES": "3", "RTSP_FIXTURE_FALLBACK": "", "CLEANUP_ON_MONITOR_START": "false",
        "SNAPSHOT_DIR": "bench/runtime/diagnostico-snapshots",
        "REPLAY_DIR": "bench/runtime/diagnostico-clips", "TRILHAS_DIR": "bench/runtime/diagnostico-trilhas", "PYTHONUNBUFFERED": "1",
    } | dict(kv.split("=", 1) for kv in a.env)
    py = sys.executable
    subprocess.run([py, "-m", "flask", "--app", "wsgi", "users", "create", "--email", "t@d.local", "--name", "T",
                    "--role", "technical", "--password", senha], cwd=RAIZ, env=env, check=True, capture_output=True)
    log = (runtime / "diagnostico-foco.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([py, "run.py"], cwd=RAIZ, env=env, stdout=log, stderr=subprocess.STDOUT)
    parar = threading.Event()
    try:
        limite = time.monotonic() + 180
        while time.monotonic() < limite:
            try:
                if requests.get(base + "/api/auth/me", timeout=1).status_code in (200, 401):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        s = requests.Session()
        s.post(base + "/api/auth/login", json={"email": "t@d.local", "password": senha}, timeout=10).raise_for_status()
        ids = {}
        for nome in ("multidao", "bench", "queda", "multidao2"):
            arquivo = fetch_fixtures.caminho_da_fixture(nome if nome != "multidao2" else "bench")
            r = s.post(base + "/api/cameras", json={"name": nome, "source_type": "Arquivo", "source": str(arquivo),
                                                   "fps": 12, "width": 960, "height": 540}, timeout=10)
            ids[nome] = r.json()["id"]
        foco = ids[a.foco]
        if a.zona:
            s.patch(f"{base}/features?camera_id={foco}", json={"features": {"ppe": False}}, timeout=10)
            zona = [{"x": 0.6, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.6, "y": 1.0}]
            s.put(f"{base}/api/cameras/{foco}/risk-area", json={"polygon": zona, "name": "Zona"}, timeout=10)
        for cid in ids.values():
            s.post(f"{base}/api/cameras/{cid}/start", timeout=120)

        def assistir() -> None:
            try:
                with s.get(f"{base}/api/cameras/{foco}/video_feed", stream=True, timeout=30) as resp:
                    for _ in resp.iter_content(65536):
                        if parar.is_set():
                            break
            except requests.RequestException:
                pass

        threading.Thread(target=assistir, daemon=True).start()
        liberado_em = None
        portal: list[dict] = []
        if a.portal:
            comeco = time.monotonic()
            for _ in range(max(1, a.repeticoes)):
                # Gravar a portaria zera o estado e os contadores brutos do portal.
                s.put(f"{base}/api/cameras/{foco}/gate", json={"required": ["helmet", "vest"]}, timeout=10)
                inicio = time.monotonic()
                medida = {"liberado_em_s": None}
                while time.monotonic() - inicio < a.segundos:
                    estado = s.get(f"{base}/api/cameras/{foco}/portal", timeout=10).json()
                    if estado.get("verdict") == "approved":
                        medida["liberado_em_s"] = round(time.monotonic() - inicio, 1)
                        break
                    time.sleep(0.2)
                medida |= estado.get("diagnostico") or {}
                portal.append(medida)
                print(json.dumps(medida, ensure_ascii=False), flush=True)
            liberado_em = portal[0]["liberado_em_s"]
            a.segundos = round(time.monotonic() - comeco)
        else:
            time.sleep(a.segundos)
        d = s.get(f"{base}/api/diagnostics/pipeline?janela_s={int(a.segundos)}", timeout=10).json()
        eventos = s.get(f"{base}/events?limit=500", timeout=10).json().get("items", [])
    finally:
        parar.set()
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
    ag = d.get("agendador") or {}
    por = ag.get("por_camera", {})
    total = sum(v["servidos"] for v in por.values()) or 1
    saida = {
        "foco": a.foco, "segundos": a.segundos, "env": a.env,
        "servidos": {nome: por.get(str(cid), {}).get("servidos") for nome, cid in ids.items()},
        "fracao_foco": round(por.get(str(foco), {}).get("servidos", 0) / total, 3),
        "maior_espera_s": {nome: por.get(str(cid), {}).get("maior_espera_s") for nome, cid in ids.items()},
        "esperas_acima_de_3s": {nome: f'{por.get(str(cid), {}).get("esperas_acima_de_3s")}/{por.get(str(cid), {}).get("vagas")}'
                                for nome, cid in ids.items()},
        "inferencias_por_s": round(total / a.segundos, 2),
        "pre_alertas_registrados": sum(1 for e in eventos if e.get("event_type") == "approach_risk_area"),
        "alertas_de_queda": sum(1 for e in eventos if "Queda" in (e.get("message") or "")),
        "portal_liberado_em_s": liberado_em if a.portal else None,
        "portal": portal,
    }
    destino = RAIZ / "bench" / "results" / f"diagnostico-foco-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(saida, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
