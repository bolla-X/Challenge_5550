from __future__ import annotations

from flask import Blueprint, current_app, jsonify

monitor_bp = Blueprint("monitor", __name__)


@monitor_bp.post("/start")
def start_monitoring():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.start())


@monitor_bp.post("/stop")
def stop_monitoring():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.stop())
