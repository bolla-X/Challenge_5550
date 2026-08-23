from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from flask_socketio import SocketIO

from app.models import Alert
from app.repositories.alert_repository import AlertRepository
from app.services.risk_rules import RuleAlert

logger = logging.getLogger(__name__)


@dataclass
class AlertRuntimeState:
    key: str
    rule_alert: RuleAlert
    violation_frames: int = 0
    normal_frames: int = 0
    alert: Alert | None = None


class AlertStateService:
    """Mantém alertas operacionais ativos e resolve quando a condição normal retorna.

    Banco mantém histórico; dashboard recebe somente o estado ativo/resolvido via WebSocket.
    """

    def __init__(
        self,
        repository: AlertRepository,
        socketio: SocketIO,
        *,
        create_after_frames: int = 3,
        resolve_after_frames: int = 5,
    ) -> None:
        self.repository = repository
        self.socketio = socketio
        self.create_after_frames = max(1, int(create_after_frames))
        self.resolve_after_frames = max(1, int(resolve_after_frames))
        self._states: dict[str, AlertRuntimeState] = {}

    def process(self, current_violations: list[RuleAlert]) -> dict[str, Any]:
        current_by_key = {item.key: item for item in current_violations}
        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        created_or_updated: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = []

        for key, item in current_by_key.items():
            state = self._states.get(key)
            if state is None:
                state = AlertRuntimeState(key=key, rule_alert=item)
                self._states[key] = state
            state.rule_alert = item
            state.violation_frames += 1
            state.normal_frames = 0

            if state.alert is None and state.violation_frames >= self.create_after_frames:
                state.alert = self.repository.create(
                    rule=item.rule,
                    severity=item.severity,
                    message=item.message,
                    feature=item.feature,
                    metadata=item.metadata | {"confirmation_frames": state.violation_frames},
                    status="active",
                )
                payload = state.alert.to_dict()
                created.append(payload)
                created_or_updated.append(payload)
                self.socketio.emit("alert_created", payload)
                self.socketio.emit("alert", payload)  # compatibilidade com clientes antigos
                logger.warning("alert_created", extra={"alert": payload})
            elif state.alert is not None and state.alert.status == "active":
                state.alert = self.repository.touch(
                    state.alert,
                    metadata=item.metadata | {"confirmation_frames": state.violation_frames},
                )
                payload = state.alert.to_dict()
                updated.append(payload)
                created_or_updated.append(payload)
                self.socketio.emit("alert_updated", payload)

        for key in list(self._states.keys()):
            if key in current_by_key:
                continue
            state = self._states[key]
            state.normal_frames += 1
            state.violation_frames = 0
            if state.normal_frames >= self.resolve_after_frames:
                if state.alert is not None and state.alert.status == "active":
                    state.alert = self.repository.resolve(
                        state.alert,
                        metadata=(state.alert.metadata_json or {}) | {"resolution_frames": state.normal_frames},
                    )
                    payload = state.alert.to_dict()
                    resolved.append(payload)
                    self.socketio.emit("alert_resolved", payload)
                    logger.info("alert_resolved", extra={"alert": payload})
                del self._states[key]

        active = self.active_alerts()
        self.socketio.emit("active_alerts", {"items": active, "count": len(active)})
        return {"active": active, "changed": created_or_updated, "created": created, "updated": updated, "resolved": resolved}

    def active_alerts(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for state in self._states.values():
            if state.alert is not None and state.alert.status == "active":
                items.append(state.alert.to_dict())
        return sorted(items, key=lambda item: item.get("severity", ""), reverse=True)


    def resolve_all(self, *, reason: str = "manual_reset") -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for key in list(self._states.keys()):
            state = self._states[key]
            if state.alert is not None and state.alert.status == "active":
                state.alert = self.repository.resolve(
                    state.alert,
                    metadata=(state.alert.metadata_json or {}) | {"resolution_reason": reason},
                )
                payload = state.alert.to_dict()
                resolved.append(payload)
                self.socketio.emit("alert_resolved", payload)
        self._states.clear()
        self.socketio.emit("active_alerts", {"items": [], "count": 0})
        return resolved

    def reset(self) -> None:
        self._states.clear()
