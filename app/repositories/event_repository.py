from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import EventLog


class EventRepository:
    def create(
        self,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        subject: str | None = None,
        metadata: dict[str, Any] | None = None,
        camera_id: int | None = None,
    ) -> EventLog:
        event = EventLog(
            camera_id=camera_id,
            event_type=event_type,
            severity=severity,
            message=message,
            subject=subject,
            metadata_json=metadata or {},
        )
        db.session.add(event)
        db.session.commit()
        return event

    def list_recent(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        severity: str | None = None,
        camera_id: int | None = None,
    ) -> list[EventLog]:
        query = EventLog.query
        if event_type:
            query = query.filter(EventLog.event_type == event_type)
        if severity:
            query = query.filter(EventLog.severity == severity)
        if camera_id is not None:
            query = query.filter(EventLog.camera_id == camera_id)
        return query.order_by(EventLog.created_at.desc()).limit(limit).all()

    def create_alert_resolved_once(
        self,
        *,
        alert_payload: dict[str, Any],
        message: str | None = None,
        severity: str = "info",
        subject: str | None = None,
        metadata: dict[str, Any] | None = None,
        camera_id: int | None = None,
    ) -> EventLog | None:
        """Cria um evento de timeline para alerta resolvido sem duplicar o mesmo alert_id."""
        alert_id = alert_payload.get("id")
        camera_id = camera_id if camera_id is not None else alert_payload.get("camera_id")
        if alert_id is None:
            return self.create(
                event_type="alert_resolved",
                message=message or alert_payload.get("message") or "Alerta resolvido",
                severity=severity,
                subject=subject,
                camera_id=camera_id,
                metadata=(metadata or {}) | {"alert": alert_payload},
            )

        # Checagem de duplicata no SQL. Antes isto carregava as 500 últimas
        # linhas e comparava em Python — a cada alerta resolvido, no meio do
        # loop de captura.
        duplicate = (
            db.session.query(EventLog.id)
            .filter(
                EventLog.event_type == "alert_resolved",
                EventLog.metadata_json["alert_id"].as_string() == str(alert_id),
            )
            .first()
        )
        if duplicate is not None:
            return None

        event_metadata = {"alert_id": str(alert_id), "alert": alert_payload}
        if metadata:
            event_metadata.update(metadata)
        return self.create(
            event_type="alert_resolved",
            message=message or alert_payload.get("message") or "Alerta resolvido",
            severity=severity,
            subject=subject,
            camera_id=camera_id,
            metadata=event_metadata,
        )
