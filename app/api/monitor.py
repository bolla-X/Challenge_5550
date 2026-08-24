from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.models import ROLE_OPERATOR
from app.utils.auth import escopo_ou_erro, require_role

monitor_bp = Blueprint("monitor", __name__)


@monitor_bp.post("/start")
@require_role(ROLE_OPERATOR)
def start_monitoring():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.start(camera_id=camera_id))


@monitor_bp.post("/stop")
@require_role(ROLE_OPERATOR)
def stop_monitoring():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.stop(camera_id=camera_id))
