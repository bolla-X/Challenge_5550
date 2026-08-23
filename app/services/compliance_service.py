from __future__ import annotations

from typing import Any

from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.vision.person_compliance_matcher import PersonComplianceMatcher
from app.vision.schemas import Detection, PoseResult


class ComplianceService:
    def __init__(self, feature_manager: FeatureManager, rule_engine: RuleEngine) -> None:
        self.feature_manager = feature_manager
        self.rule_engine = rule_engine
        self.person_matcher = PersonComplianceMatcher()

    def build_state(
        self,
        *,
        detections: list[Detection],
        pose: PoseResult | None,
        frame_shape: tuple[int, int, int],
        model_diagnostics: dict[str, Any],
        active_alerts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        labels = {item.label for item in detections}
        people_detections = [item for item in detections if item.label == "person" or item.category == "person"]
        person_present = bool(people_detections) or bool(pose and pose.found)
        supported_ppe = model_diagnostics.get("supported_ppe", {}) or {}
        rule_alerts = self.rule_engine.evaluate(detections, pose, frame_shape)
        active_by_feature = {item.get("feature"): item for item in active_alerts if item.get("status") == "active"}
        enabled_ppe = {
            "helmet": self.feature_manager.is_enabled("ppe") and self.feature_manager.is_enabled("helmet"),
            "vest": self.feature_manager.is_enabled("ppe") and self.feature_manager.is_enabled("vest"),
            "gloves": self.feature_manager.is_enabled("ppe") and self.feature_manager.is_enabled("gloves"),
        }
        people = self.person_matcher.build(
            detections,
            supported_ppe=supported_ppe,
            enabled_ppe=enabled_ppe,
            risk_polygon=self.rule_engine.risk_polygon if self.feature_manager.is_enabled("risk_area") else None,
            frame_shape=frame_shape,
        )

        checks = [
            ("helmet", "Capacete"),
            ("vest", "Colete"),
            ("gloves", "Luvas"),
        ]
        ppe: dict[str, dict[str, Any]] = {}
        for key, label in checks:
            if not self.feature_manager.is_enabled("ppe") or not self.feature_manager.is_enabled(key):
                status = "disabled"
                message = "Feature desativada"
            elif not supported_ppe.get(key, False):
                status = "unsupported"
                message = "Classe não suportada pelo modelo YOLO atual"
            elif people:
                missing_people = [person for person in people if person["ppe"][key]["status"] == "missing"]
                uncertain_people = [person for person in people if person["ppe"][key]["status"] == "unsupported"]
                ok_people = [person for person in people if person["ppe"][key]["status"] == "ok"]
                if missing_people:
                    status = "missing"
                    message = f"Ausente em {len(missing_people)} de {len(people)} pessoa(s)"
                elif uncertain_people:
                    status = "unsupported"
                    message = "Modelo não suporta avaliação completa"
                elif ok_people:
                    status = "ok"
                    message = f"Detectado em {len(ok_people)} pessoa(s)"
                else:
                    status = "waiting"
                    message = "Aguardando associação por pessoa"
            elif key in labels:
                status = "ok"
                message = "Detectado"
            elif person_present:
                status = "missing"
                message = "Ausente"
            else:
                status = "waiting"
                message = "Aguardando pessoa no frame"
            ppe[key] = {
                "key": key,
                "label": label,
                "status": status,
                "message": message,
                "enabled": self.feature_manager.is_enabled("ppe") and self.feature_manager.is_enabled(key),
                "supported": bool(supported_ppe.get(key, False)),
                "detections": [item.to_dict() for item in detections if item.label == key],
                "active_alert": active_by_feature.get(key),
            }

        pose_state = self._pose_state(pose, active_by_feature)
        risk_state = self._risk_state(rule_alerts, active_by_feature, people)

        return {
            "person_present": person_present,
            "person_count": len(people) if people else (1 if pose and pose.found else 0),
            "people": people,
            "ppe": ppe,
            "pose": pose_state,
            "risk_area": risk_state,
            "model": model_diagnostics,
            "active_alerts": active_alerts,
        }

    def _pose_state(self, pose: PoseResult | None, active_by_feature: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if not self.feature_manager.is_enabled("pose"):
            return {"enabled": False, "status": "disabled", "message": "Feature desativada"}
        if not pose or not pose.found:
            return {"enabled": True, "status": "waiting", "message": "Pose não detectada"}
        if active_by_feature.get("falls"):
            return {"enabled": True, "status": "critical", "message": "Queda detectada", "active_alert": active_by_feature.get("falls")}
        if active_by_feature.get("posture"):
            return {"enabled": True, "status": "warning", "message": "Postura suspeita", "active_alert": active_by_feature.get("posture")}
        return {"enabled": True, "status": "ok", "message": "Pose normal"}

    def _risk_state(
        self,
        rule_alerts: list[Any],
        active_by_feature: dict[str, dict[str, Any]],
        people: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.feature_manager.is_enabled("risk_area"):
            return {"enabled": False, "status": "disabled", "message": "Feature desativada"}
        risk_people = [person for person in people if person.get("risk_area", {}).get("status") == "inside"]
        if active_by_feature.get("risk_area") or any(item.feature == "risk_area" for item in rule_alerts):
            detail = f"{len(risk_people)} pessoa(s) em área de risco" if risk_people else "Pessoa em área de risco"
            return {"enabled": True, "status": "warning", "message": detail, "active_alert": active_by_feature.get("risk_area")}
        return {"enabled": True, "status": "ok", "message": "Área livre"}
