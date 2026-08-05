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
    ) -> EventLog:
        event = EventLog(
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
    ) -> list[EventLog]:
        query = EventLog.query
        if event_type:
            query = query.filter(EventLog.event_type == event_type)
        if severity:
            query = query.filter(EventLog.severity == severity)
        return query.order_by(EventLog.created_at.desc()).limit(limit).all()

    def create_alert_resolved_once(
        self,
        *,
        alert_payload: dict[str, Any],
        message: str | None = None,
        severity: str = "info",
        subject: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventLog | None:
        """Cria um evento de timeline para alerta resolvido sem duplicar o mesmo alert_id."""
        alert_id = alert_payload.get("id")
        if alert_id is None:
            return self.create(
                event_type="alert_resolved",
                message=message or alert_payload.get("message") or "Alerta resolvido",
                severity=severity,
                subject=subject,
                metadata=(metadata or {}) | {"alert": alert_payload},
            )

        existing_items = EventLog.query.filter(EventLog.event_type == "alert_resolved").order_by(EventLog.created_at.desc()).limit(500).all()
        for existing in existing_items:
            if str((existing.metadata_json or {}).get("alert_id")) == str(alert_id):
                return None

        event_metadata = {"alert_id": str(alert_id), "alert": alert_payload}
        if metadata:
            event_metadata.update(metadata)
        return self.create(
            event_type="alert_resolved",
            message=message or alert_payload.get("message") or "Alerta resolvido",
            severity=severity,
            subject=subject,
            metadata=event_metadata,
        )
