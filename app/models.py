from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    rule = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(30), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    feature = db.Column(db.String(80), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="active", index=True)
    frame_ref = db.Column(db.String(240), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    occurrences = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    first_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    @property
    def key(self) -> str:
        metadata = self.metadata_json or {}
        subject = metadata.get("person_id") or metadata.get("subject") or "global"
        return f"{self.rule}:{self.feature or 'global'}:{subject}"

    def to_dict(self) -> dict:
        metadata = self.metadata_json or {}
        return {
            "id": self.id,
            "key": self.key,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "feature": self.feature,
            "status": self.status,
            "frame_ref": self.frame_ref,
            "metadata": metadata,
            "false_positive": bool(metadata.get("false_positive")),
            "occurrences": self.occurrences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class EventLog(db.Model):
    __tablename__ = "event_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(30), nullable=False, default="info", index=True)
    message = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(120), nullable=True, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "subject": self.subject,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
