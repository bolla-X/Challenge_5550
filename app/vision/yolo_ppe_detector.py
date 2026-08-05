from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

import numpy as np

from app.vision.schemas import BoundingBox, Detection

logger = logging.getLogger(__name__)


PPE_CLASS_ALIASES = {
    "helmet": "helmet",
    "helmets": "helmet",
    "hardhat": "helmet",
    "hard_hat": "helmet",
    "hard hat": "helmet",
    "safety helmet": "helmet",
    "safety_helmet": "helmet",
    "construction helmet": "helmet",
    "vest": "vest",
    "vests": "vest",
    "safety vest": "vest",
    "safety_vest": "vest",
    "reflective vest": "vest",
    "reflective_vest": "vest",
    "hi-vis vest": "vest",
    "hivis vest": "vest",
    "glove": "gloves",
    "gloves": "gloves",
    "safety gloves": "gloves",
    "safety_gloves": "gloves",
    "work gloves": "gloves",
    "person": "person",
    "worker": "person",
}

PPE_REQUIRED_CLASSES = ("helmet", "vest", "gloves")


class YoloPPEDetector:
    def __init__(
        self,
        model_path: str,
        confidence: float = 0.35,
        device: str | None = None,
        classes: list[int] | None = None,
        max_detections: int = 100,
    ) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self.device = device
        self.classes = classes
        self.max_detections = max(1, int(max_detections))
        self._last_diagnostics: dict[str, Any] | None = None

    @cached_property
    def model(self):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Pacote ultralytics não instalado. Rode pip install -r requirements.txt") from exc
        logger.info("loading_yolo_model", extra={"model_path": self.model_path})
        return YOLO(self.model_path)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            device=self.device,
            classes=self.classes,
            verbose=False,
            max_det=self.max_detections,
        )
        detections: list[Detection] = []
        if not results:
            return detections

        result = results[0]
        names = getattr(result, "names", {}) or getattr(self.model, "names", {}) or {}
        self._last_diagnostics = self._build_diagnostics(names=names, error=None)
        self._log_model_warning_once(self._last_diagnostics)

        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return detections

        for box in boxes:
            coords = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
            confidence = float(box.conf[0].detach().cpu().item()) if box.conf is not None else 0.0
            class_id = int(box.cls[0].detach().cpu().item()) if box.cls is not None else None
            raw_label = str(names.get(class_id, class_id)).strip().lower()
            normalized = self.normalize_label(raw_label)
            category = "ppe" if normalized in set(PPE_REQUIRED_CLASSES) else normalized
            detections.append(
                Detection(
                    label=normalized,
                    confidence=confidence,
                    class_id=class_id,
                    category=category,
                    box=BoundingBox(x1=coords[0], y1=coords[1], x2=coords[2], y2=coords[3]),
                )
            )
        return detections

    def diagnostics(self) -> dict[str, Any]:
        if self._last_diagnostics is not None:
            return self._last_diagnostics
        try:
            names = getattr(self.model, "names", {}) or {}
            self._last_diagnostics = self._build_diagnostics(names=names, error=None)
            self._log_model_warning_once(self._last_diagnostics)
        except Exception as exc:  # noqa: BLE001
            self._last_diagnostics = self._build_diagnostics(names={}, error=str(exc))
        return self._last_diagnostics

    def supported_ppe_classes(self) -> set[str]:
        diagnostics = self.diagnostics()
        supported = diagnostics.get("supported_ppe", {})
        return {key for key, value in supported.items() if value}

    def is_ppe_model_ready(self) -> bool:
        return bool(self.supported_ppe_classes())

    @staticmethod
    def normalize_label(label: str) -> str:
        normalized = str(label).strip().lower().replace("-", "_")
        normalized = normalized.replace("  ", " ")
        return PPE_CLASS_ALIASES.get(normalized, PPE_CLASS_ALIASES.get(normalized.replace("_", " "), normalized))

    def _build_diagnostics(self, *, names: dict[Any, Any], error: str | None) -> dict[str, Any]:
        normalized_by_id = []
        normalized_values: set[str] = set()
        for raw_id, raw_name in dict(names or {}).items():
            try:
                class_id = int(raw_id)
            except (TypeError, ValueError):
                class_id = raw_id
            name = str(raw_name).strip().lower()
            normalized = self.normalize_label(name)
            normalized_values.add(normalized)
            normalized_by_id.append({"id": class_id, "name": name, "normalized": normalized})

        supported_ppe = {key: key in normalized_values for key in PPE_REQUIRED_CLASSES}
        has_person = "person" in normalized_values
        ready = all(supported_ppe.values()) and has_person
        warning = None
        if error:
            warning = f"Modelo YOLO indisponível: {error}"
        elif not any(supported_ppe.values()):
            warning = "O modelo YOLO carregado não possui classes de EPI. Configure PPE_MODEL_PATH com pesos treinados para helmet/vest/gloves."
        elif not ready:
            missing = [key for key, enabled in supported_ppe.items() if not enabled]
            if not has_person:
                missing.append("person")
            warning = f"Modelo YOLO parcial para EPI. Classes ausentes: {', '.join(missing)}."

        return {
            "model_path": self.model_path,
            "confidence": self.confidence,
            "device": self.device,
            "class_filter": self.classes,
            "max_detections": self.max_detections,
            "raw_class_count": len(normalized_by_id),
            "classes": normalized_by_id,
            "supported_ppe": supported_ppe,
            "person_supported": has_person,
            "ppe_ready": ready,
            "warning": warning,
            "error": error,
        }

    def _log_model_warning_once(self, diagnostics: dict[str, Any]) -> None:
        if diagnostics.get("warning") and not getattr(self, "_warning_logged", False):
            logger.warning("ppe_model_diagnostics_warning", extra={"diagnostics": diagnostics})
            self._warning_logged = True
