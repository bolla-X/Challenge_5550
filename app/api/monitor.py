from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.models import ROLE_OPERATOR
from app.utils.auth import require_role

monitor_bp = Blueprint("monitor", __name__)


@monitor_bp.post("/start")
@require_role(ROLE_OPERATOR)
def start_monitoring():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.start())


@monitor_bp.post("/stop")
@require_role(ROLE_OPERATOR)
def stop_monitoring():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.stop())
