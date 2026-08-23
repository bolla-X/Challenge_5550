from __future__ import annotations

from app.repositories.alert_repository import AlertRepository


def test_status_endpoint(client):
    response = client.get("/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["system"] == "VisionEPI"
    assert payload["running"] is False


def test_start_stop_endpoints(client):
    start = client.post("/start")
    assert start.status_code == 200
    assert start.get_json()["running"] is True

    stop = client.post("/stop")
    assert stop.status_code == 200
    assert stop.get_json()["running"] is False


def test_features_update_endpoint(client):
    response = client.patch("/features", json={"features": {"helmet": False, "falls": True}})
    assert response.status_code == 200
    features = {item["key"]: item for item in response.get_json()["features"]}
    assert features["helmet"]["enabled"] is False
    assert features["falls"]["enabled"] is True


def test_alerts_endpoint(client, app):
    with app.app_context():
        AlertRepository().create(rule="missing_helmet", severity="critical", message="Sem capacete", feature="helmet")
    response = client.get("/alerts")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["items"][0]["rule"] == "missing_helmet"


def test_events_endpoint(client):
    response = client.get("/events")
    assert response.status_code == 200
    assert "items" in response.get_json()


def test_risk_area_endpoint(client):
    response = client.patch("/risk-area", json={"polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.5}]})
    assert response.status_code == 200
    assert len(response.get_json()["risk_area"]["polygon"]) == 3


def test_false_positive_endpoint(client, app):
    with app.app_context():
        alert = AlertRepository().create(rule="missing_vest", severity="high", message="Sem colete", feature="vest")
        alert_id = alert.id
    response = client.post(f"/alerts/{alert_id}/false-positive", json={"reason": "teste"})
    assert response.status_code == 200
    payload = response.get_json()["alert"]
    assert payload["false_positive"] is True
    assert payload["status"] == "resolved"
