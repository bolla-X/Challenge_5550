"""G8: API do Modo TV — agregado por setor, metas só do supervisor."""

from __future__ import annotations

from app.extensions import db
from app.models import Camera


def test_tv_agrega_por_setor_sem_dado_por_pessoa(real_monitor_app):
    with real_monitor_app.app_context():
        db.session.add_all([Camera(name="Doca 1", location="Expedição", source_type="USB", source="0"),
                            Camera(name="Doca 2", location="Expedição", source_type="USB", source="1"),
                            Camera(name="Portaria", source_type="USB", source="2")])
        db.session.commit()
    dados = real_monitor_app.test_client().get("/api/tv").get_json()
    setores = {s["setor"]: s for s in dados["setores"]}
    assert set(setores) >= {"Expedição", "Portaria"}
    assert len(setores["Expedição"]["cameras"]) == 2
    texto = repr(dados)
    assert "person_" not in texto and "track_id" not in texto


def test_metas_validam_e_aparecem_no_setor(real_monitor_app):
    cliente = real_monitor_app.test_client()
    assert cliente.put("/api/tv/metas/Expedição", json={"minutos_conformes": 0}).status_code == 400
    assert cliente.put("/api/tv/metas/Expedição", json={"minutos_conformes": True}).status_code == 400
    r = cliente.put("/api/tv/metas/Expedição", json={"minutos_conformes": 120, "checkins_portal": 30})
    assert r.status_code == 200 and r.get_json()["minutos_conformes"] == 120
    metas = cliente.get("/api/tv/metas").get_json()["metas"]
    assert metas == [{"setor": "Expedição", "minutos_conformes": 120, "checkins_portal": 30}]
