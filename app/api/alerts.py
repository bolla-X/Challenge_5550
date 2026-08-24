from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app.models import ROLE_OPERATOR
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.utils.auth import login_required, require_role

logger = logging.getLogger(__name__)

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.get("/alerts")
@login_required
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
    alerts = AlertRepository().list_recent(
        limit=limit,
        severity=severity,
        status=status,
        false_positive=false_positive,
        camera_id=request.args.get("camera_id", type=int),
    )
    return jsonify({"items": [item.to_dict() for item in alerts], "count": len(alerts)})


@alerts_bp.get("/alerts/<int:alert_id>/evidence")
@login_required
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
@require_role(ROLE_OPERATOR)
def mark_false_positive(alert_id: int):
    payload = request.get_json(silent=True) or {}
    repository = AlertRepository()
    alert = repository.get(alert_id)
    if alert is None:
        return jsonify({"error": "alerta não encontrado"}), 404
    reason = str(payload.get("reason", "")).strip() or None
    alert = repository.mark_false_positive(alert, reason=reason)
    alert_payload = alert.to_dict()

    event = _log_and_broadcast(
        alert,
        alert_payload,
        message=f"Alerta resolvido como falso positivo: {alert.message}",
        metadata={"reason": reason, "false_positive": True},
        broadcast_resolved=True,
    )
    return jsonify({"alert": alert_payload, "event": event})


@alerts_bp.post("/alerts/<int:alert_id>/acknowledge")
@require_role(ROLE_OPERATOR)
def acknowledge_alert(alert_id: int):
    """Operador confirma que tratou o alerta em campo ("avisei o colaborador").

    Não resolve o alerta — quem resolve é a detecção parar de ver a violação
    (AlertStateService). Isto só registra na linha do tempo QUEM agiu e QUANDO,
    que é o que a auditoria precisa. Antes o botão correspondente no kiosk era
    um window.alert() dizendo "mock, ainda não persiste".
    """
    payload = request.get_json(silent=True) or {}
    repository = AlertRepository()
    alert = repository.get(alert_id)
    if alert is None:
        return jsonify({"error": "alerta não encontrado"}), 404

    note = str(payload.get("note", "")).strip()[:200] or None
    alert = repository.acknowledge(alert, note=note)
    alert_payload = alert.to_dict()

    event = _log_and_broadcast(
        alert,
        alert_payload,
        message=f"Colaborador avisado: {alert.message}",
        metadata={"acknowledged": True, "note": note},
        broadcast_resolved=False,
    )
    return jsonify({"alert": alert_payload, "event": event})


def _subject_of(alert) -> str | None:
    metadata = alert.metadata_json or {}
    return metadata.get("person_label") or metadata.get("person_id") or alert.feature


def _log_and_broadcast(alert, alert_payload: dict, *, message: str, metadata: dict, broadcast_resolved: bool) -> dict | None:
    """Grava o evento de timeline e avisa os clientes conectados.

    Falha aqui não pode derrubar a ação do operador (o alerta JÁ foi gravado no
    banco), mas também não pode sumir sem rastro como sumia antes num
    `except: pass`.
    """
    monitor = current_app.extensions.get("monitor_service")
    socketio = getattr(monitor, "socketio", None) or current_app.extensions.get("socketio")
    try:
        if broadcast_resolved:
            event = EventRepository().create_alert_resolved_once(
                alert_payload=alert_payload,
                severity="info",
                message=message,
                subject=_subject_of(alert),
                metadata=metadata,
            )
        else:
            event = EventRepository().create(
                event_type="alert_acknowledged",
                severity="info",
                message=message,
                subject=_subject_of(alert),
                camera_id=alert.camera_id,
                metadata=metadata | {"alert_id": str(alert.id), "alert": alert_payload},
            )
        event_payload = event.to_dict() if event is not None else None

        if socketio is not None:
            if event_payload is not None:
                socketio.emit("timeline_event", event_payload)
            if broadcast_resolved:
                socketio.emit("alert_resolved", alert_payload)
                active = getattr(monitor, "alert_state_service", None)
                if active is not None:
                    items = active.active_alerts()
                    socketio.emit("active_alerts", {"camera_id": alert.camera_id, "items": items, "count": len(items)})
            else:
                socketio.emit("alert_updated", alert_payload)
        return event_payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert_action_broadcast_failed", extra={"alert_id": alert.id, "error": str(exc)})
        return None
