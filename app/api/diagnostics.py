from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app.config import BASE_DIR
from app.repositories.event_repository import EventRepository

runtime_bp = Blueprint("runtime", __name__)


@runtime_bp.get("/model")
def model_diagnostics():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.status().get("model", {}))


@runtime_bp.get("/settings")
def get_settings():
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"settings": monitor.settings(), "overlay": monitor.get_overlay()})


@runtime_bp.patch("/settings")
def patch_settings():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload inválido"}), 400
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"settings": monitor.update_settings(payload)})


@runtime_bp.get("/overlay")
def get_overlay():
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"overlay": monitor.get_overlay()})


@runtime_bp.patch("/overlay")
def patch_overlay():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload inválido"}), 400
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"overlay": monitor.update_overlay(payload)})


@runtime_bp.get("/risk-area")
def get_risk_area():
    monitor = current_app.extensions["monitor_service"]
    if not hasattr(monitor, "risk_area_state"):
        return jsonify({"error": "monitor atual não suporta área de risco runtime"}), 501
    return jsonify({"risk_area": monitor.risk_area_state()})


@runtime_bp.patch("/risk-area")
def patch_risk_area():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload inválido"}), 400
    monitor = current_app.extensions["monitor_service"]
    if not hasattr(monitor, "update_risk_area"):
        return jsonify({"error": "monitor atual não suporta área de risco runtime"}), 501
    try:
        return jsonify({"risk_area": monitor.update_risk_area(payload)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@runtime_bp.get("/events")
def list_events():
    try:
        limit = min(int(request.args.get("limit", 80)), 300)
    except ValueError:
        limit = 80
    event_type = request.args.get("event_type")
    severity = request.args.get("severity")
    events = EventRepository().list_recent(limit=limit, event_type=event_type, severity=severity)
    return jsonify({"items": [item.to_dict() for item in events], "count": len(events)})


@runtime_bp.get("/snapshots/<path:filename>")
def get_snapshot(filename: str):
    monitor = current_app.extensions.get("monitor_service")
    snapshot_dir = "runtime/snapshots"
    if monitor is not None and hasattr(monitor, "snapshot_service"):
        snapshot_dir = monitor.snapshot_service.snapshot_dir
    directory = Path(snapshot_dir)
    if not directory.is_absolute():
        directory = Path(BASE_DIR) / directory
    return send_from_directory(directory, filename, as_attachment=False)
