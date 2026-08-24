from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.feature_manager import FeatureManager
from app.vision.person_compliance_matcher import PersonComplianceMatcher
from app.vision.schemas import Detection, PoseResult


@dataclass(frozen=True)
class RuleAlert:
    rule: str
    severity: str
    message: str
    feature: str
    metadata: dict[str, Any]

    @property
    def key(self) -> str:
        subject = self.metadata.get("person_id") or self.metadata.get("subject") or "global"
        return f"{self.rule}:{self.feature}:{subject}"


class RuleEngine:
    def __init__(
        self,
        feature_manager: FeatureManager,
        cooldown_seconds: int,
        risk_polygon: list[tuple[float, float]],
        supported_ppe_getter: Callable[[], set[str]] | None = None,
    ) -> None:
        self.feature_manager = feature_manager
        self.cooldown_seconds = cooldown_seconds
        self.risk_polygon = risk_polygon
        self.supported_ppe_getter = supported_ppe_getter
        self.person_matcher = PersonComplianceMatcher()

    def evaluate(self, detections: list[Detection], pose: PoseResult | None, frame_shape: tuple[int, int, int]) -> list[RuleAlert]:
        alerts: list[RuleAlert] = []
        alerts.extend(self._evaluate_ppe(detections, pose, frame_shape))
        alerts.extend(self._evaluate_pose(pose))
        alerts.extend(self._evaluate_risk_area(detections, pose, frame_shape))
        return alerts

    def _evaluate_ppe(self, detections: list[Detection], pose: PoseResult | None, frame_shape: tuple[int, int, int]) -> list[RuleAlert]:
        if not self.feature_manager.is_enabled("ppe"):
            return []

        supported_ppe = self.supported_ppe_getter() if self.supported_ppe_getter else {"helmet", "vest", "gloves"}
        labels = {item.label for item in detections}
        people = [item for item in detections if item.label == "person" or item.category == "person"]
        person_present = bool(people) or bool(pose and pose.found)
        alerts: list[RuleAlert] = []

        checks = [
            ("helmet", "helmet", "Sem capacete", "critical"),
            ("vest", "vest", "Sem colete", "high"),
            ("gloves", "gloves", "Sem luvas", "medium"),
            ("glasses", "glasses", "Sem óculos de proteção", "high"),
        ]

        if people:
            enabled_ppe = {key: self.feature_manager.is_enabled(key) for key, *_ in checks}
            supported_map = {key: key in supported_ppe for key, *_ in checks}
            person_states = self.person_matcher.build(
                detections,
                supported_ppe=supported_map,
                enabled_ppe=enabled_ppe,
                risk_polygon=self.risk_polygon,
                frame_shape=frame_shape,
            )
            for person_state in person_states:
                for feature_key, required_label, message, severity in checks:
                    if not self.feature_manager.is_enabled(feature_key) or required_label not in supported_ppe:
                        continue
                    ppe_state = person_state["ppe"][feature_key]
                    if ppe_state["status"] == "missing":
                        alerts.append(
                            RuleAlert(
                                rule=f"missing_{required_label}",
                                severity=severity,
                                message=f"{message} — {person_state['label']}",
                                feature=feature_key,
                                metadata={
                                    "person_id": person_state["id"],
                                    "person_label": person_state["label"],
                                    "person_box": person_state["box"],
                                    "present_labels": sorted(labels),
                                    "supported_ppe": sorted(supported_ppe),
                                },
                            )
                        )
            return alerts

        for feature_key, required_label, message, severity in checks:
            if not self.feature_manager.is_enabled(feature_key):
                continue
            if required_label not in supported_ppe:
                continue
            if person_present and required_label not in labels:
                alerts.append(
                    RuleAlert(
                        rule=f"missing_{required_label}",
                        severity=severity,
                        message=message,
                        feature=feature_key,
                        metadata={"subject": "global", "present_labels": sorted(labels), "supported_ppe": sorted(supported_ppe)},
                    )
                )
        return alerts

    def _evaluate_pose(self, pose: PoseResult | None) -> list[RuleAlert]:
        if not pose or not pose.found or not self.feature_manager.is_enabled("pose"):
            return []

        alerts: list[RuleAlert] = []
        if self.feature_manager.is_enabled("falls") and self._is_fallen(pose):
            alerts.append(
                RuleAlert(
                    rule="fallen_person",
                    severity="critical",
                    message="Pessoa caída detectada",
                    feature="falls",
                    metadata={"subject": "global_pose", "method": "torso_orientation"},
                )
            )
        if self.feature_manager.is_enabled("posture") and self._is_bad_posture(pose):
            alerts.append(
                RuleAlert(
                    rule="suspicious_posture",
                    severity="medium",
                    message="Postura suspeita detectada",
                    feature="posture",
                    metadata={"subject": "global_pose", "method": "shoulder_hip_alignment"},
                )
            )
        return alerts

    def _is_fallen(self, pose: PoseResult) -> bool:
        left_shoulder = pose.by_name("left_shoulder")
        right_shoulder = pose.by_name("right_shoulder")
        left_hip = pose.by_name("left_hip")
        right_hip = pose.by_name("right_hip")
        required = [left_shoulder, right_shoulder, left_hip, right_hip]
        if any(item is None or item.visibility < 0.4 for item in required):
            return False
        shoulder_x = (left_shoulder.x + right_shoulder.x) / 2
        shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
        hip_x = (left_hip.x + right_hip.x) / 2
        hip_y = (left_hip.y + right_hip.y) / 2
        torso_dx = abs(shoulder_x - hip_x)
        torso_dy = abs(shoulder_y - hip_y)
        return torso_dx > torso_dy * 1.6

    def _is_bad_posture(self, pose: PoseResult) -> bool:
        left_shoulder = pose.by_name("left_shoulder")
        right_shoulder = pose.by_name("right_shoulder")
        left_hip = pose.by_name("left_hip")
        right_hip = pose.by_name("right_hip")
        nose = pose.by_name("nose")
        required = [left_shoulder, right_shoulder, left_hip, right_hip, nose]
        if any(item is None or item.visibility < 0.4 for item in required):
            return False
        shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
        hip_y = (left_hip.y + right_hip.y) / 2
        torso_height = max(0.001, hip_y - shoulder_y)
        head_forward_offset = abs(nose.x - ((left_shoulder.x + right_shoulder.x) / 2))
        excessive_forward = head_forward_offset > 0.18
        compressed_torso = torso_height < 0.10
        return bool(excessive_forward or compressed_torso)

    def _evaluate_risk_area(self, detections: list[Detection], pose: PoseResult | None, frame_shape: tuple[int, int, int]) -> list[RuleAlert]:
        if not self.feature_manager.is_enabled("risk_area"):
            return []

        height, width = frame_shape[:2]
        alerts: list[RuleAlert] = []
        people = sorted(
            [item for item in detections if item.label == "person" or item.category == "person"],
            key=lambda item: (item.box.x1, item.box.y1),
        )
        for index, detection in enumerate(people, start=1):
            cx, cy = detection.box.center
            point = (cx / width, cy / height)
            if self._point_in_polygon(point, self.risk_polygon):
                person_id = f"person_{index}"
                alerts.append(
                    RuleAlert(
                        rule="risk_area_presence",
                        severity="high",
                        message=f"Pessoa em área de risco — Pessoa {index}",
                        feature="risk_area",
                        metadata={
                            "person_id": person_id,
                            "person_label": f"Pessoa {index}",
                            "person_box": detection.box.to_dict(),
                            "point": {"x": round(point[0], 4), "y": round(point[1], 4)},
                            "polygon": self.risk_polygon,
                        },
                    )
                )

        if alerts:
            return alerts

        if pose and pose.found:
            left_hip = pose.by_name("left_hip")
            right_hip = pose.by_name("right_hip")
            if left_hip and right_hip:
                point = ((left_hip.x + right_hip.x) / 2, (left_hip.y + right_hip.y) / 2)
                if self._point_in_polygon(point, self.risk_polygon):
                    return [
                        RuleAlert(
                            rule="risk_area_presence",
                            severity="high",
                            message="Pessoa em área de risco",
                            feature="risk_area",
                            metadata={"subject": "global_pose", "point": {"x": round(point[0], 4), "y": round(point[1], 4)}, "polygon": self.risk_polygon},
                        )
                    ]
        return []

    @staticmethod
    def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
        x, y = point
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / max(yj - yi, 1e-12) + xi)
            if intersects:
                inside = not inside
            j = i
        return inside
