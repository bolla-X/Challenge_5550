from __future__ import annotationsfrom dataclasses import dataclassfrom typing import Any, Callablefrom app.services.feature_manager import FeatureManagerfrom app.vision.person_compliance_matcher import PPE_KEYS, PersonComplianceMatcherfrom app.vision.schemas import Detection, PoseResult# feature -> (mensagem, severidade). Fonte única das regras de EPI: a mesma
# lista de tuplas aparecia duplicada em dois pontos deste arquivo.
PPE_RULES: dict[str, tuple[str, str]] = {
    "helmet": ("Sem capacete", "critical"),
    "vest": ("Sem colete", "high"),
    "gloves": ("Sem luvas", "medium"),
    "glasses": ("Sem óculos de proteção", "high"),
    "mask": ("Sem máscara", "medium"),
    "safety_shoe": ("Sem calçado de segurança", "medium"),
}


@dataclass(frozen=True)
class RuleEvaluation:
    """Resultado de UMA passada do motor de regras sobre o frame.

    `people` é o estado de conformidade por pessoa que o matcher já produziu
    para decidir os alertas. Ele volta junto porque o ComplianceService precisa
    exatamente do mesmo dado: antes ele chamava `evaluate()` de novo e refazia
    o matching, então cada frame rodava o RuleEngine 2x e o
    PersonComplianceMatcher 3x.
    """

    alerts: list[RuleAlert]
    people: list[dict[str, Any]]


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

    def analyze(self, detections: list[Detection], pose: PoseResult | None, frame_shape: tuple[int, int, int]) -> RuleEvaluation:
        """Passada única: monta o estado por pessoa uma vez e deriva todos os
        alertas dele. Use isto no loop de captura; `evaluate()` continua
        existindo para quem só quer os alertas."""
        people = self.build_people(detections, frame_shape)
        alerts: list[RuleAlert] = []
        alerts.extend(self._evaluate_ppe(detections, pose, people))
        alerts.extend(self._evaluate_pose(pose))
        alerts.extend(self._evaluate_risk_area(people, pose))
        return RuleEvaluation(alerts=alerts, people=people)

    def evaluate(self, detections: list[Detection], pose: PoseResult | None, frame_shape: tuple[int, int, int]) -> list[RuleAlert]:
        return self.analyze(detections, pose, frame_shape).alerts

    def supported_ppe(self) -> set[str]:
        return self.supported_ppe_getter() if self.supported_ppe_getter else set(PPE_KEYS)

    def build_people(self, detections: list[Detection], frame_shape: tuple[int, int, int]) -> list[dict[str, Any]]:
        """Estado de conformidade por pessoa. Fonte ÚNICA — RuleEngine e
        ComplianceService leem daqui em vez de cada um construir o seu."""
        supported = self.supported_ppe()
        ppe_enabled = self.feature_manager.is_enabled("ppe")
        return self.person_matcher.build(
            detections,
            supported_ppe={key: key in supported for key in PPE_KEYS},
            enabled_ppe={key: ppe_enabled and self.feature_manager.is_enabled(key) for key in PPE_KEYS},
            risk_polygon=self.risk_polygon if self.feature_manager.is_enabled("risk_area") else None,
            frame_shape=frame_shape,
        )

    def _evaluate_ppe(self, detections: list[Detection], pose: PoseResult | None, people: list[dict[str, Any]]) -> list[RuleAlert]:
        if not self.feature_manager.is_enabled("ppe"):
            return []

        supported_ppe = self.supported_ppe()
        labels = {item.label for item in detections}
        person_present = bool(people) or bool(pose and pose.found)
        alerts: list[RuleAlert] = []

        if people:
            for person_state in people:
                for feature_key, (message, severity) in PPE_RULES.items():
                    if not self.feature_manager.is_enabled(feature_key) or feature_key not in supported_ppe:
                        continue
                    if person_state["ppe"][feature_key]["status"] != "missing":
                        continue
                    alerts.append(
                        RuleAlert(
                            rule=f"missing_{feature_key}",
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

        # Sem nenhuma caixa de pessoa: cai para o sinal global da pose, que não
        # distingue indivíduos (é uma pose só por frame).
        for feature_key, (message, severity) in PPE_RULES.items():
            if not self.feature_manager.is_enabled(feature_key) or feature_key not in supported_ppe:
                continue
            if person_present and feature_key not in labels:
                alerts.append(
                    RuleAlert(
                        rule=f"missing_{feature_key}",
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

    def _evaluate_risk_area(self, people: list[dict[str, Any]], pose: PoseResult | None) -> list[RuleAlert]:
        if not self.feature_manager.is_enabled("risk_area"):
            return []

        # `people` já traz risk_area.status calculado pelo matcher — sem
        # recomputar ponto-em-polígono nem reordenar as detecções aqui.
        alerts = [
            RuleAlert(
                rule="risk_area_presence",
                severity="high",
                message=f"Pessoa em área de risco — {person['label']}",
                feature="risk_area",
                metadata={
                    "person_id": person["id"],
                    "person_label": person["label"],
                    "person_box": person["box"],
                    "point": person["risk_area"].get("point"),
                    "polygon": self.risk_polygon,
                },
            )
            for person in people
            if person.get("risk_area", {}).get("status") == "inside"
        ]
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
                            metadata={
                                "subject": "global_pose",
                                "point": {"x": round(point[0], 4), "y": round(point[1], 4)},
                                "polygon": self.risk_polygon,
                            },
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
