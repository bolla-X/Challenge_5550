from __future__ import annotations

from app.repositories.alert_repository import AlertRepository
from app.services import risk_score_service as svc


def _create(feature: str, severity: str) -> None:
    AlertRepository().create(rule=f"missing_{feature}", severity=severity, message="x", feature=feature)


def test_no_alerts_gives_zero_score(app):
    with app.app_context():
        result = svc.compute_risk_score()
        assert result["overall"]["score"] == 0.0
        assert result["overall"]["level"] == "baixo"
        assert result["overall"]["driving_feature"] is None
        assert all(item["score"] == 0.0 for item in result["features"].values())


def test_score_scales_with_configurable_max_points(app, monkeypatch):
    with app.app_context():
        _create("helmet", "critical")  # 4 pontos
        monkeypatch.setattr(svc, "RISK_SCORE_MAX_POINTS", 4.0)
        result = svc.compute_risk_score()
        assert result["features"]["helmet"]["score"] == 100.0
        assert result["features"]["helmet"]["alert_count"] == 1
        assert result["overall"]["driving_feature"] == "helmet"

        monkeypatch.setattr(svc, "RISK_SCORE_MAX_POINTS", 40.0)
        result = svc.compute_risk_score()
        assert result["features"]["helmet"]["score"] == 10.0
        assert result["features"]["helmet"]["level"] == "baixo"


def test_overall_is_worst_feature_not_sum(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(svc, "RISK_SCORE_MAX_POINTS", 10.0)
        _create("gloves", "low")  # 1 ponto -> 10%
        _create("helmet", "critical")  # 4 pontos -> 40%
        result = svc.compute_risk_score()
        assert result["overall"]["score"] == 40.0
        assert result["overall"]["driving_feature"] == "helmet"
        assert result["features"]["gloves"]["score"] == 10.0


def test_old_alerts_outside_window_are_excluded(app):
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        _create("helmet", "critical")
        alert = AlertRepository().list_recent(limit=1)[0]
        alert.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=svc.RISK_SCORE_WINDOW_MINUTES + 5)
        from app.extensions import db

        db.session.commit()

        result = svc.compute_risk_score()
        assert result["features"]["helmet"]["alert_count"] == 0


def test_trend_buckets_alerts_by_hour(app, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.extensions import db

    with app.app_context():
        monkeypatch.setattr(svc, "RISK_SCORE_MAX_POINTS", 4.0)
        now = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)

        _create("helmet", "critical")  # will be moved to "2 hours ago" bucket
        _create("gloves", "critical")  # stays in "now" (most recent) bucket

        alerts = AlertRepository().list_recent(limit=2)
        old_alert = next(a for a in alerts if a.feature == "helmet")
        old_alert.last_seen_at = now - timedelta(hours=2, minutes=10)
        db.session.commit()

        result = svc.compute_risk_trend(hours=3, bucket_hours=1, now=now)
        assert result["hours"] == 3
        assert len(result["buckets"]) == 3

        oldest_bucket, middle_bucket, latest_bucket = result["buckets"]
        assert oldest_bucket["features"]["helmet"]["alert_count"] == 1
        assert oldest_bucket["features"]["helmet"]["score"] == 100.0
        assert middle_bucket["overall"]["score"] == 0.0
        assert latest_bucket["features"]["gloves"]["alert_count"] == 1


def test_trend_empty_bucket_has_zero_score(app):
    with app.app_context():
        result = svc.compute_risk_trend(hours=2, bucket_hours=1)
        assert len(result["buckets"]) == 2
        assert all(b["overall"]["score"] == 0.0 for b in result["buckets"])
