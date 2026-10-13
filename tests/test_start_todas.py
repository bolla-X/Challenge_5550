"""Iniciar da topbar liga TODAS as câmeras (Técnico/Supervisor), não só a padrão."""

from __future__ import annotations

from app.extensions import db
from app.models import Camera


def test_start_todas_liga_cada_camera(real_monitor_app):
    with real_monitor_app.app_context():
        db.session.add_all([Camera(name="A", source_type="USB", source="0"), Camera(name="B", source_type="USB", source="1")])
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        cliente = real_monitor_app.test_client()
        resposta = cliente.post("/start?todas=1")
        assert resposta.status_code == 200
        assert all(estado["running"] for estado in monitor.status_all().values()), "a segunda câmera ficou parada"
        assert len(resposta.get_json()["todas"]) == 2
        cliente.post("/stop?todas=1")
        assert not any(estado["running"] for estado in monitor.status_all().values())


def test_sem_todas_continua_so_a_padrao(real_monitor_app):
    with real_monitor_app.app_context():
        db.session.add_all([Camera(name="A", source_type="USB", source="0"), Camera(name="B", source_type="USB", source="1")])
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        real_monitor_app.test_client().post("/start")
        assert sum(1 for estado in monitor.status_all().values() if estado["running"]) == 1
        monitor.stop_all()
