"""Modo demonstração: `python run.py --demo` e `flask demo reset`.

O que a demo é, e o que não é:

- banco ISOLADO (`instance/demo/demo.db`), recriado a cada `--demo`; nada do
  banco do dia a dia é tocado;
- três contas (supervisor, técnico, operador) com senha gerada na hora e
  impressa SÓ no terminal — não vai para arquivo nem para log;
- câmeras das gravações de demonstração (`tests/fixtures/`, rotuladas
  "GRAVAÇÃO" na tela) e, se a webcam abrir, uma câmera "AO VIVO" no Portal;
- offline: LLM desligado, nenhum download (as gravações precisam estar
  baixadas: `python scripts/fetch_fixtures.py`);
- tema claro por padrão (quem já escolheu um tema no navegador mantém o seu).

`flask demo reset` (< 10 s): com o servidor da demo no ar, pede o reset a ele
(o estado das câmeras está na memória do servidor, não no banco), autenticado
por um token aleatório que só existe em `instance/demo/token` nesta máquina.
Sem servidor no ar, limpa direto o banco da demo.
"""

from __future__ import annotations

import os
import secrets
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.demo_ambiente import (  # noqa: F401  (reexportados para quem importa app.demo)
    BANCO,
    EPIS_DESLIGADOS_NA_DEMO,
    FIXTURES,
    GRAVACOES,
    METAS,
    PASTA,
    PLANTA_PATIO,
    PLANTAS,
    TOKEN,
    ZONA_PATIO,
    preparar_ambiente,
)


def _features_da_demo() -> dict[str, bool]:
    from app.models import DEFAULT_CAMERA_FEATURES

    return {k: (k not in EPIS_DESLIGADOS_NA_DEMO) and v for k, v in DEFAULT_CAMERA_FEATURES.items()}


def webcam_disponivel(indice: int = 0) -> bool:
    import cv2

    cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(indice)
    try:
        return bool(cap.isOpened() and cap.read()[0])
    finally:
        cap.release()


def semear(app) -> dict[str, Any]:
    """Contas, câmeras, zona, planta, portal e metas. Devolve as senhas (só para imprimir)."""
    from app.extensions import db
    from app.models import Camera, MetaDoSetor
    from app.services.auth_service import AuthService

    with app.app_context():
        cameras: dict[str, Camera] = {}
        for nome, setor, arquivo in GRAVACOES:
            cam = Camera(name=nome, location=setor, source_type="Arquivo", source=str(FIXTURES / arquivo),
                         fps=12, width=960, height=540, features_json=_features_da_demo())
            db.session.add(cam)
            cameras[nome] = cam
        ao_vivo = webcam_disponivel(0)
        if ao_vivo:
            cam = Camera(name="Portal", location="Portaria", source_type="USB", source="0", fps=12, width=640, height=480,
                         features_json=_features_da_demo(), gate_required=["helmet", "vest"])
            db.session.add(cam)
            cameras["Portal"] = cam
        else:
            cameras["Canteiro"].gate_required = ["helmet", "vest"]
        cameras["Pátio"].risk_polygon = ZONA_PATIO
        for nome, calibracao in PLANTAS.items():
            cameras[nome].planta = calibracao
        for setor, meta in METAS.items():
            db.session.add(MetaDoSetor(setor=setor, **meta))
        db.session.commit()

        senhas = {papel: secrets.token_urlsafe(12) for papel in ("supervisor", "technical", "operator")}
        servico = AuthService()
        servico.create_user(email="supervisor@demo.local", name="Supervisora da demo", password=senhas["supervisor"],
                            role="supervisor")
        servico.create_user(email="tecnico@demo.local", name="Técnico da demo", password=senhas["technical"],
                            role="technical")
        alvo = cameras["Portal"] if ao_vivo else cameras["Canteiro"]
        servico.create_user(email="operador@demo.local", name="Operador da demo", password=senhas["operator"],
                            role="operator", camera_id=alvo.id)
        return {"senhas": senhas, "ao_vivo": ao_vivo, "cameras": {n: c.id for n, c in cameras.items()}}


def imprimir_acessos(info: dict[str, Any], porta: int) -> None:
    s = info["senhas"]
    print("\n[demo] VisionEPI em modo demonstração (banco isolado, offline).", flush=True)
    print(f"[demo] Abra http://127.0.0.1:{porta}", flush=True)
    print(f"[demo]   supervisor@demo.local  {s['supervisor']}", flush=True)
    print(f"[demo]   tecnico@demo.local     {s['technical']}", flush=True)
    print(f"[demo]   operador@demo.local    {s['operator']}", flush=True)
    print("[demo] Webcam: " + ("ligada como câmera AO VIVO \"Portal\"." if info["ao_vivo"]
                                else "não encontrada; o Portal usa a gravação do Canteiro."), flush=True)
    print("[demo] Senhas valem só para esta execução. Reset: flask --app wsgi demo reset\n", flush=True)


def resetar_no_servidor(app) -> dict[str, Any]:
    """Executado DENTRO do servidor da demo: para tudo, limpa o histórico e religa
    com workers NOVOS (zera histerese, Andon, portal e sinais, que vivem na memória)."""
    from app.extensions import db
    from app.models import Alert, ElodeCustodia, EventLog, Incidente

    inicio = time.monotonic()
    monitor = app.extensions["monitor_service"]
    fases: dict[str, float] = {}

    def marca(nome: str) -> None:
        fases[nome] = round(time.monotonic() - inicio, 2)

    with app.app_context():
        # Em paralelo: cada `stop()` espera até 2 s pela thread de captura, e em
        # sequência as 4 câmeras levavam o reset para 12,6 s (meta: < 10 s).
        with monitor._workers_lock:
            workers = dict(monitor._workers)
            monitor._workers.clear()
        with ThreadPoolExecutor(max_workers=max(1, len(workers))) as pool:
            list(pool.map(lambda w: w.stop(), workers.values()))
        marca("parou")
        Alert.query.delete()
        EventLog.query.delete()
        Incidente.query.delete()
        # A cadeia de custódia acompanha as evidências que a demo apaga.
        ElodeCustodia.query.delete()
        db.session.commit()
        for sub in ("clips", "snapshots"):
            shutil.rmtree(PASTA / sub, ignore_errors=True)
        fila = getattr(monitor, "fila_de_rotulos", None)
        if fila is not None:
            for sub in ("fila", "confirmados", "rejeitados"):
                shutil.rmtree(fila.pasta / sub, ignore_errors=True)
                (fila.pasta / sub).mkdir(parents=True, exist_ok=True)
        marca("limpou")
        monitor.load_cameras_from_db()
        marca("recriou")
        with monitor._workers_lock:
            novos = list(monitor._workers.values())
        with ThreadPoolExecutor(max_workers=max(1, len(novos))) as pool:
            list(pool.map(lambda w: w.start(), novos))
        marca("religou")
        n = len(monitor._workers)
    return {"ok": True, "segundos": round(time.monotonic() - inicio, 2), "cameras": n, "fases_s": fases}
