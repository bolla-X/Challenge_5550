from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_from_directory

from app.utils.auth import escopo_ou_erro, login_required

status_bp = Blueprint("status", __name__)


@status_bp.get("/")
@status_bp.get("/dashboard")
@status_bp.get("/dashboard/")
def index():
    # Serve o shell do build React (frontend/vite.config.ts emite aqui).
    # O caminho Jinja antigo (app/templates/ + app/static/app.js|styles.css)
    # foi removido do disco — nenhuma rota o referenciava desde a migração.
    dist_dir = Path(current_app.static_folder) / "dist"
    return send_from_directory(dist_dir, "index.html")


@status_bp.get("/status")
@login_required
def status():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"system": "VisionEPI", **monitor.status(camera_id=camera_id)})


@status_bp.get("/preflight")
@login_required
def preflight():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.preflight(camera_id=camera_id))
