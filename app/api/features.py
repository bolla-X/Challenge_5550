from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_TECHNICAL
from app.utils.auth import login_required, require_role

features_bp = Blueprint("features", __name__)


@features_bp.get("/features")
@login_required
def get_features():
    manager = current_app.extensions["feature_manager"]
    return jsonify({"features": [item.to_dict() for item in manager.list()]})


@features_bp.put("/features")
@features_bp.patch("/features")
@require_role(ROLE_TECHNICAL)
def update_features():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload inválido. Use {'features': {'helmet': true}}"}), 400
    updates = payload.get("features", payload)
    if not isinstance(updates, dict):
        return jsonify({"error": "Payload inválido. Use {'features': {'helmet': true}}"}), 400
    manager = current_app.extensions["feature_manager"]
    updated = manager.update({str(key): bool(value) for key, value in updates.items()})
    response = {"features": [item.to_dict() for item in updated]}
    current_app.extensions["monitor_service"].socketio.emit("features_updated", response)
    return jsonify(response)
