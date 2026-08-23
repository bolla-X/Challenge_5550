from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models import Alert


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AlertRepository:
    def create(
        self,
        *,
        rule: str,
        severity: str,
        message: str,
        feature: str | None = None,
        metadata: dict[str, Any] | None = None,
        frame_ref: str | None = None,
        status: str = "active",
    ) -> Alert:
        now = utc_now()
        alert = Alert(
            rule=rule,
            severity=severity,
            message=message,
            feature=feature,
            metadata_json=metadata or {},
            frame_ref=frame_ref,
            status=status,
            occurrences=1,
            created_at=now,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.session.add(alert)
        db.session.commit()
        return alert

    def get(self, alert_id: int) -> Alert | None:
        return db.session.get(Alert, int(alert_id))

    def touch(self, alert: Alert, *, metadata: dict[str, Any] | None = None) -> Alert:
        alert.last_seen_at = utc_now()
        alert.occurrences = int(alert.occurrences or 0) + 1
        if metadata is not None:
            alert.metadata_json = metadata
        db.session.commit()
        return alert

    def resolve(self, alert: Alert, *, metadata: dict[str, Any] | None = None) -> Alert:
        now = utc_now()
        alert.status = "resolved"
        alert.last_seen_at = now
        alert.resolved_at = now
        if metadata is not None:
            alert.metadata_json = metadata
        db.session.commit()
        return alert

    def update_frame_ref(self, alert: Alert, frame_ref: str) -> Alert:
        alert.frame_ref = frame_ref
        metadata = alert.metadata_json or {}
        metadata["snapshot_available"] = True
        alert.metadata_json = metadata
        db.session.commit()
        return alert

    def mark_false_positive(self, alert: Alert, *, reason: str | None = None) -> Alert:
        metadata = alert.metadata_json or {}
        metadata["false_positive"] = True
        if reason:
            metadata["false_positive_reason"] = reason
        metadata["false_positive_at"] = utc_now().isoformat()
        metadata["resolution_reason"] = metadata.get("resolution_reason") or "false_positive"
        if alert.status == "active":
            alert.status = "resolved"
            alert.resolved_at = utc_now()
        alert.last_seen_at = utc_now()
        alert.metadata_json = metadata
        db.session.commit()
        return alert

    def list_recent(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        status: str | None = None,
        false_positive: bool | None = None,
    ) -> list[Alert]:
        query = Alert.query
        if severity:
            query = query.filter(Alert.severity == severity)
        if status:
            query = query.filter(Alert.status == status)
        items = query.order_by(Alert.last_seen_at.desc()).limit(limit).all()
        if false_positive is not None:
            items = [item for item in items if bool((item.metadata_json or {}).get("false_positive")) is false_positive]
        return items

    def resolve_all_active(self, *, reason: str = "startup_reset") -> int:
        active_alerts = Alert.query.filter(Alert.status == "active").all()
        now = utc_now()
        for alert in active_alerts:
            alert.status = "resolved"
            alert.last_seen_at = now
            alert.resolved_at = now
            metadata = alert.metadata_json or {}
            metadata["resolution_reason"] = reason
            alert.metadata_json = metadata
        db.session.commit()
        return len(active_alerts)

    def list_active(self, *, limit: int = 100) -> list[Alert]:
        return self.list_recent(limit=limit, status="active")
