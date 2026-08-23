from __future__ import annotations

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


class DummySocket:
    def emit(self, *args, **kwargs):
        return None


class DummyMonitor:
    def __init__(self, feature_manager):
        self.socketio = DummySocket()
        self.feature_manager = feature_manager
        self.started = False

    def status(self):
        return {
            "running": self.started,
            "frame_counter": 0,
            "last_error": None,
            "features": self.feature_manager.as_dict(),
        }

    def start(self):
        self.started = True
        return self.status()

    def stop(self):
        self.started = False
        return self.status()

    def latest_analysis(self):
        return {}

    def latest_jpeg(self):
        return None

    def settings(self):
        return {"target_fps": 12, "snapshot_enabled": True}

    def get_overlay(self):
        return {"boxes": True, "labels": True, "confidence": True, "pose": True, "risk_area": True}

    def update_settings(self, updates):
        current = self.settings()
        current.update(updates)
        return current

    def update_overlay(self, updates):
        current = self.get_overlay()
        current.update(updates)
        return current

    def risk_area_state(self):
        return {"name": "Área de risco", "polygon": [{"x": 0.7, "y": 0.1}, {"x": 0.98, "y": 0.1}, {"x": 0.98, "y": 0.95}], "enabled": True}

    def update_risk_area(self, payload):
        return {"name": payload.get("name", "Área de risco"), "polygon": payload["polygon"], "enabled": True}


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        feature_manager = app.extensions["feature_manager"]
        app.extensions["monitor_service"] = DummyMonitor(feature_manager)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
