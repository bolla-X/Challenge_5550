from __future__ import annotations

from app.repositories.alert_repository import AlertRepository
from app.services.alert_state_service import AlertStateService
from app.services.risk_rules import RuleAlert


class DummySocket:
    def __init__(self):
        self.events = []

    def emit(self, event, payload=None, *args, **kwargs):
        self.events.append((event, payload))


def missing_helmet():
    return RuleAlert(
        rule="missing_helmet",
        severity="critical",
        message="Sem capacete",
        feature="helmet",
        metadata={"present_labels": ["person"]},
    )


def test_alert_state_creates_and_resolves_after_confirmation_frames(app):
    with app.app_context():
        socket = DummySocket()
        service = AlertStateService(AlertRepository(), socket, create_after_frames=2, resolve_after_frames=2)

        first = service.process([missing_helmet()])
        assert first["active"] == []

        second = service.process([missing_helmet()])
        assert len(second["active"]) == 1
        assert second["active"][0]["status"] == "active"
        assert any(event == "alert_created" for event, _ in socket.events)

        still_active = service.process([])
        assert len(still_active["active"]) == 1

        resolved = service.process([])
        assert resolved["active"] == []
        assert len(resolved["resolved"]) == 1
        assert resolved["resolved"][0]["status"] == "resolved"
        assert any(event == "alert_resolved" for event, _ in socket.events)
