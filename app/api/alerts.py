from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.get("/alerts")
def list_alerts():
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except ValueError:
        limit = 100
    severity = request.args.get("severity")
    status = request.args.get("status")
    false_positive_raw = request.args.get("false_positive")
    false_positive = None
    if false_positive_raw is not None and false_positive_raw != "":
        false_positive = false_positive_raw.lower() in {"1", "true", "yes", "on"}
    if status and status not in {"active", "resolved"}:
        return jsonify({"error": "status deve ser 'active' ou 'resolved'"}), 400
    alerts = AlertRepository().list_recent(limit=limit, severity=severity, status=status, false_positive=false_positive)
    return jsonify({"items": [item.to_dict() for item in alerts], "count": len(alerts)})


@alerts_bp.get("/alerts/<int:alert_id>/evidence")
def get_alert_evidence(alert_id: int):
    alert = AlertRepository().get(alert_id)
    if alert is None:
        return jsonify({"error": "alerta não encontrado"}), 404
    if not alert.frame_ref:
        return jsonify({"error": "alerta sem evidência vinculada"}), 404

    filename = Path(str(alert.frame_ref)).name
    if not filename:
        return jsonify({"error": "referência de evidência inválida"}), 404

    monitor = current_app.extensions.get("monitor_service")
    if monitor is None or not hasattr(monitor, "snapshot_service"):
        return jsonify({"error": "serviço de evidências indisponível"}), 503

    directory = monitor.snapshot_service.absolute_dir
    filepath = directory / filename
    if not filepath.exists():
        return jsonify({"error": "arquivo de evidência não encontrado", "filename": filename}), 404
    return send_from_directory(directory, filename, as_attachment=False)


@alerts_bp.post("/alerts/<int:alert_id>/false-positive")
def mark_false_positive(alert_id: int):
    payload = request.get_json(silent=True) or {}
    repository = AlertRepository()
    alert = repository.get(alert_id)
    if alert is None:
        return jsonify({"error": "alerta não encontrado"}), 404
    reason = str(payload.get("reason", "")).strip() or None
    alert = repository.mark_false_positive(alert, reason=reason)
    alert_payload = alert.to_dict()

    try:
        event = EventRepository().create_alert_resolved_once(
            alert_payload=alert_payload,
            severity="info",
            message=f"Alerta resolvido como falso positivo: {alert.message}",
            subject=(alert.metadata_json or {}).get("person_label") or (alert.metadata_json or {}).get("person_id") or alert.feature,
            metadata={"reason": reason, "false_positive": True},
        )
        socketio = current_app.extensions.get("socketio")
        monitor = current_app.extensions.get("monitor_service")
        if monitor is not None and hasattr(monitor, "socketio"):
            monitor.socketio.emit("timeline_event", event.to_dict()) if event is not None else None
            monitor.socketio.emit("alert_resolved", alert_payload)
            monitor.socketio.emit("active_alerts", {"items": monitor.alert_state_service.active_alerts(), "count": len(monitor.alert_state_service.active_alerts())}) if hasattr(monitor, "alert_state_service") else None
        elif socketio is not None:
            socketio.emit("timeline_event", event.to_dict()) if event is not None else None
    except Exception:  # noqa: BLE001
        pass

    return jsonify({"alert": alert_payload})
