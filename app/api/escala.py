"""Prova de escala (F10): sobe N câmeras virtuais de uma fixture, ao vivo.

Responde à pergunta que a banca faz sempre — "e com 10 câmeras?" — com número
medido na frente dela, não com slide: cada câmera virtual é um worker de
verdade (captura, agendador, regras), lendo a mesma fixture. O painel mostra o
FPS publicado e analisado por câmera e a idade da análise conforme N cresce.

As câmeras virtuais são marcadas (`location = "virtual · prova de escala"`) e
removidas pelo DELETE — inclusive as que sobraram de uma prova interrompida.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.config import BASE_DIR
from app.extensions import db
from app.models import DEFAULT_CAMERA_FEATURES, ROLE_TECHNICAL, Camera
from app.utils.auth import require_role

escala_bp = Blueprint("escala", __name__)

MARCA = "virtual · prova de escala"
FIXTURE_PADRAO = "tests/fixtures/next_multidao.mp4"
MAX_CAMERAS = 12


def _virtuais() -> list[Camera]:
    return Camera.query.filter_by(location=MARCA).order_by(Camera.id.asc()).all()


@escala_bp.post("/api/escala")
@require_role(ROLE_TECHNICAL)
def iniciar_prova():
    payload = request.get_json(silent=True) or {}
    try:
        n = max(1, min(MAX_CAMERAS, int(payload.get("n", 4))))
    except (TypeError, ValueError):
        return jsonify({"error": "'n' deve ser um inteiro"}), 400
    fixture = Path(BASE_DIR) / str(current_app.config.get("ESCALA_FIXTURE", FIXTURE_PADRAO))
    if not fixture.exists():
        return jsonify({"error": f"fixture ausente: {fixture.name}. Rode python scripts/fetch_fixtures.py"}), 409
    existentes = _virtuais()
    for i in range(len(existentes), n):
        camera = Camera(name=f"Escala {i + 1}", location=MARCA, source_type="Arquivo", source=str(fixture),
                        fps=10, width=960, height=540, features_json=dict(DEFAULT_CAMERA_FEATURES))
        db.session.add(camera)
    for camera in existentes[n:]:
        db.session.delete(camera)
    db.session.commit()
    monitor = current_app.extensions["monitor_service"]
    monitor.load_cameras_from_db()
    ids = [c.id for c in _virtuais()]
    for cid in ids:
        monitor.start(camera_id=cid)
    return jsonify({"cameras": ids, "n": len(ids)})


@escala_bp.delete("/api/escala")
@require_role(ROLE_TECHNICAL)
def encerrar_prova():
    virtuais = _virtuais()
    monitor = current_app.extensions["monitor_service"]
    for camera in virtuais:
        try:
            monitor.stop(camera_id=camera.id)
        except LookupError:
            pass
        db.session.delete(camera)
    db.session.commit()
    monitor.load_cameras_from_db()
    return jsonify({"removidas": len(virtuais)})


@escala_bp.get("/api/escala")
@require_role(ROLE_TECHNICAL)
def estado_da_prova():
    ids = [c.id for c in _virtuais()]
    monitor = current_app.extensions["monitor_service"]
    diag = monitor.diagnostico_do_pipeline(ids, janela_s=10.0) if ids else {"cameras": {}}
    linhas = []
    for cid in ids:
        st = (diag["cameras"].get(str(cid)) or {}).get("stats", {})
        taxas, etapas = st.get("taxas_por_s", {}), st.get("etapas", {})
        linhas.append({
            "camera_id": cid,
            "fps_publicado": taxas.get("frames_publicados", 0.0),
            "fps_analisado": taxas.get("inferencias", 0.0),
            "idade_analise_p95_ms": (etapas.get("idade_na_inferencia") or {}).get("p95"),
        })
    return jsonify({"n": len(ids), "cameras": linhas, "adaptativo": diag.get("adaptativo")})
