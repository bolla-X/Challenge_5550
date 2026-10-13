from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_OPERATOR
from app.utils.auth import camera_scope, escopo_ou_erro, require_role

monitor_bp = Blueprint("monitor", __name__)


@monitor_bp.post("/start")
@require_role(ROLE_OPERATOR)
def start_monitoring():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    # ?todas=1 (Técnico/Supervisor): liga TODAS as câmeras. O botão da topbar
    # ligava só a câmera padrão e, numa demo com duas, a segunda ficava parada
    # e parecia que o multicâmera não funcionava. Operador segue no escopo dele.
    if request.args.get("todas") == "1" and camera_scope() is None and hasattr(monitor, "start_all"):
        todas = monitor.start_all()
        return jsonify(monitor.status(camera_id=camera_id) | {"todas": {str(k): v.get("running") for k, v in todas.items()}})
    return jsonify(monitor.start(camera_id=camera_id))


@monitor_bp.post("/stop")
@require_role(ROLE_OPERATOR)
def stop_monitoring():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    if request.args.get("todas") == "1" and camera_scope() is None and hasattr(monitor, "stop_all"):
        todas = monitor.stop_all()
        return jsonify(monitor.status(camera_id=camera_id) | {"todas": {str(k): v.get("running") for k, v in todas.items()}})
    return jsonify(monitor.stop(camera_id=camera_id))
