"""Gêmeo digital (X1): /api/gemeo junta as câmeras calibradas numa planta só."""

from __future__ import annotations

from app.extensions import db
from app.models import Camera
from app.vision.planta import estado_de_conformidade

CAL = {"pontos_camera": [[0.2, 0.5], [0.8, 0.5], [1.0, 1.0], [0.0, 1.0]],
       "pontos_planta": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.6], [0.1, 0.6]]}


def test_estado_do_avatar_nao_trata_nao_verificavel_como_ausente():
    pessoa = {"ppe": {"helmet": {"status": "ok"}, "gloves": {"status": "not_verifiable"}}, "risk_area": {"status": "outside"}}
    assert estado_de_conformidade(pessoa) == {"estado": "conforme", "faltando": []}
    pessoa["ppe"]["helmet"]["status"] = "missing"
    assert estado_de_conformidade(pessoa) == {"estado": "sem_epi", "faltando": ["helmet"]}
    pessoa["ppe"]["helmet"]["status"] = "ok"
    pessoa["risk_area"]["status"] = "inside"
    assert estado_de_conformidade(pessoa)["estado"] == "zona"
    pessoa["pose"] = {"fallen": True}
    assert estado_de_conformidade(pessoa)["estado"] == "emergencia"


def test_api_junta_camera_calibrada_com_pes_zona_e_alerta(real_monitor_app, real_monitor_client):
    with real_monitor_app.app_context():
        cam = Camera(name="Pátio", location="Expedição", source_type="Arquivo", source="x.mp4", planta=CAL,
                     risk_polygon=[[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]])
        sem = Camera(name="Portal", source_type="USB", source="0")
        db.session.add_all([cam, sem])
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(cam.id)
        worker.pes_na_planta = [{"track_id": 4, "x": 0.3, "y": 0.4, "dentro_da_calibracao": True, "na_zona": False,
                                 "estado": "sem_epi", "faltando": ["helmet"]}]
        worker.alert_state_service._states = {}
        cam_id, sem_id = cam.id, sem.id

        class _Estado:
            snapshot = {"id": 77, "severity": "critical", "status": "active", "metadata": {"person_id": "person_4"}}

        worker.alert_state_service._states["k"] = _Estado()
    corpo = real_monitor_client.get("/api/gemeo").get_json()
    por_id = {c["id"]: c for c in corpo["cameras"]}
    patio = por_id[cam_id]
    assert patio["calibrada"] and patio["setor"] == "Expedição"
    assert patio["pontos_planta"] == CAL["pontos_planta"]
    assert len(patio["zona"]) == 4
    assert patio["pes"][0]["estado"] == "sem_epi" and patio["pes"][0]["alert_id"] == 77
    assert por_id[sem_id]["calibrada"] is False and por_id[sem_id]["pes"] == []
