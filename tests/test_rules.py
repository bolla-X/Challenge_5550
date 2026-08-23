from __future__ import annotations

from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.vision.schemas import BoundingBox, Detection, PoseLandmark, PoseResult


def manager():
    return FeatureManager.from_config({"DEFAULT_FEATURES": "ppe,helmet,vest,gloves,pose,falls,posture,risk_area"})


def test_missing_ppe_alerts_with_mock_detection():
    engine = RuleEngine(manager(), cooldown_seconds=0, risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)])
    detections = [Detection(label="person", confidence=0.9, box=BoundingBox(10, 10, 100, 240), category="person")]
    alerts = engine.evaluate(detections, None, (480, 640, 3))
    rules = {alert.rule for alert in alerts}
    assert "missing_helmet" in rules
    assert "missing_vest" in rules
    assert "missing_gloves" in rules


def test_fallen_pose_alert():
    engine = RuleEngine(manager(), cooldown_seconds=0, risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)])
    pose = PoseResult(
        landmarks=[
            PoseLandmark("left_shoulder", 0.20, 0.50, 0, 0.9),
            PoseLandmark("right_shoulder", 0.22, 0.52, 0, 0.9),
            PoseLandmark("left_hip", 0.70, 0.55, 0, 0.9),
            PoseLandmark("right_hip", 0.72, 0.57, 0, 0.9),
            PoseLandmark("nose", 0.21, 0.45, 0, 0.9),
        ]
    )
    alerts = engine.evaluate([], pose, (480, 640, 3))
    assert any(alert.rule == "fallen_person" for alert in alerts)


def test_risk_area_presence_from_person_box():
    engine = RuleEngine(manager(), cooldown_seconds=0, risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)])
    detections = [Detection(label="person", confidence=0.95, box=BoundingBox(500, 100, 620, 300), category="person")]
    alerts = engine.evaluate(detections, None, (480, 640, 3))
    assert any(alert.rule == "risk_area_presence" for alert in alerts)


def test_missing_ppe_alerts_are_generated_per_person():
    engine = RuleEngine(manager(), cooldown_seconds=0, risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)])
    detections = [
        Detection(label="person", confidence=0.9, box=BoundingBox(10, 10, 100, 240), category="person"),
        Detection(label="person", confidence=0.88, box=BoundingBox(150, 10, 250, 240), category="person"),
    ]
    alerts = engine.evaluate(detections, None, (480, 640, 3))
    helmet_alerts = [alert for alert in alerts if alert.rule == "missing_helmet"]
    assert len(helmet_alerts) == 2
    assert {alert.metadata["person_id"] for alert in helmet_alerts} == {"person_1", "person_2"}
