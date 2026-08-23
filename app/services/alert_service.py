from __future__ import annotations

import logging
from typing import Any

from flask_socketio import SocketIO

from app.repositories.alert_repository import AlertRepository
from app.services.risk_rules import RuleAlert

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, repository: AlertRepository, socketio: SocketIO) -> None:
        self.repository = repository
        self.socketio = socketio

    def persist_and_emit(self, rule_alerts: list[RuleAlert]) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for item in rule_alerts:
            alert = self.repository.create(
                rule=item.rule,
                severity=item.severity,
                message=item.message,
                feature=item.feature,
                metadata=item.metadata,
            )
            payload = alert.to_dict()
            persisted.append(payload)
            self.socketio.emit("alert", payload)
            logger.warning("alert_created", extra={"alert": payload})
        return persisted
