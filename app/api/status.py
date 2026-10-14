from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_from_directory

from app.utils.auth import escopo_ou_erro, login_required

status_bp = Blueprint("status", __name__)


@status_bp.get("/")
@status_bp.get("/dashboard")
@status_bp.get("/dashboard/")
@status_bp.get("/portal")
@status_bp.get("/tv")
@status_bp.get("/rotular")
@status_bp.get("/desafio")
@status_bp.get("/gemeo")
@status_bp.get("/simulador")
@status_bp.get("/auditoria")
@status_bp.get("/palco")
@status_bp.get("/palco/controle")
@status_bp.get("/retrospectiva")
@status_bp.get("/liga")
def index():
    # Serve o shell do build React (frontend/vite.config.ts emite aqui).
    # O caminho Jinja antigo (app/templates/ + app/static/app.js|styles.css)
    # foi removido do disco — nenhuma rota o referenciava desde a migração.
    dist_dir = Path(current_app.static_folder) / "dist"
    if current_app.config.get("DEMO_MODE"):
        # Demo em tema claro (projetor), salvo se a pessoa já escolheu um tema.
        html = (dist_dir / "index.html").read_text(encoding="utf-8")
        script = ("<script>try{if(!localStorage.getItem('visionepi-theme'))"
                  "localStorage.setItem('visionepi-theme','light')}catch(e){}</script>")
        return current_app.response_class(html.replace("<head>", "<head>" + script, 1), mimetype="text/html")
    return send_from_directory(dist_dir, "index.html")


@status_bp.get("/sw.js")
def service_worker():
    """Service worker do PWA (X10) servido na RAIZ: só assim o escopo dele é o app inteiro."""
    dist_dir = Path(current_app.static_folder) / "dist"
    resposta = send_from_directory(dist_dir, "sw.js", mimetype="text/javascript", max_age=0)
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@status_bp.get("/manifest.webmanifest")
def manifesto():
    dist_dir = Path(current_app.static_folder) / "dist"
    return send_from_directory(dist_dir, "manifest.webmanifest", mimetype="application/manifest+json", max_age=0)


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
