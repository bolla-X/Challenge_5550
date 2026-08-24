from __future__ import annotations

import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db


class DummySocket:
    """Coleta os emits em vez de mandar pra rede. `events` fica disponível pra
    quem quiser afirmar sobre o que foi emitido."""

    def __init__(self):
        self.events: list[tuple[str, object]] = []

    def emit(self, event, payload=None, *args, **kwargs):
        self.events.append((event, payload))

    def start_background_task(self, target, *args, **kwargs):
        # Nunca dispara a thread: nos testes ninguém quer um loop de captura
        # tentando abrir webcam. Quem precisa exercitar o loop chama-o direto.
        return None


class DummyMonitor:
    """Stub das ROTAS LEGADAS (/status, /start, /settings, ...).

    Existe só pra essas rotas, que operam sobre "a câmera padrão" e não têm
    nada de multi-câmera pra exercitar. As rotas /api/cameras/* são testadas
    contra o MonitorService REAL — ver a fixture `real_monitor_app`.
    """

    def __init__(self, feature_manager):
        self.socketio = DummySocket()
        self.feature_manager = feature_manager
        self.started = False

    def status(self, camera_id=None):
        return {
            "camera_id": None,
            "running": self.started,
            "frame_counter": 0,
            "last_error": None,
            "features": self.feature_manager.as_dict(),
        }

    def start(self, camera_id=None):
        self.started = True
        return self.status()

    def stop(self, camera_id=None):
        self.started = False
        return self.status()

    def latest_analysis(self, camera_id=None):
        return {}

    def latest_jpeg(self, camera_id=None):
        return None

    def settings(self, camera_id=None):
        return {"camera_id": None, "target_fps": 12, "snapshot_enabled": True}

    def get_overlay(self, camera_id=None):
        return {"camera_id": None, "boxes": True, "labels": True, "confidence": True, "pose": True, "risk_area": True}

    def update_settings(self, updates, camera_id=None):
        current = self.settings()
        current.update(updates)
        return current

    def update_overlay(self, updates, camera_id=None):
        current = self.get_overlay()
        current.update(updates)
        return current

    def risk_area_state(self, camera_id=None):
        return {
            "camera_id": None,
            "name": "Área de risco",
            "polygon": [{"x": 0.7, "y": 0.1}, {"x": 0.98, "y": 0.1}, {"x": 0.98, "y": 0.95}],
            "enabled": True,
        }

    def update_risk_area(self, payload, camera_id=None):
        return {"camera_id": None, "name": payload.get("name", "Área de risco"), "polygon": payload["polygon"], "enabled": True}


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


@pytest.fixture()
def real_monitor_app():
    """App com o MonitorService DE VERDADE, sem stub.

    Seguro em teste porque os pesos YOLO e o MediaPipe são carregados de forma
    preguiçosa (`cached_property`) — construir MonitorService/CameraWorker não
    toca em modelo nem em câmera. O que não pode acontecer é `start()`, que
    abriria a captura; por isso o socketio é trocado por um DummySocket cujo
    `start_background_task` não faz nada.
    """
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        monitor = app.extensions["monitor_service"]
        monitor.socketio = DummySocket()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def real_monitor_client(real_monitor_app):
    return real_monitor_app.test_client()
