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
    "goggles": "glasses",
    "goggle": "glasses",
    "glasses": "glasses",
    "safety goggles": "glasses",
    "safety_goggles": "glasses",
    "eye protection": "glasses",
    "mask": "mask",
    "masks": "mask",
    "face mask": "mask",
    "respirator": "mask",
    "safety_shoe": "safety_shoe",
    "safety shoe": "safety_shoe",
    "safety shoes": "safety_shoe",
    "boots": "safety_shoe",
    "safety boots": "safety_shoe",
    "safety cone": "safety_cone",
    "safety_cone": "safety_cone",
    "person": "person",
    "worker": "person",
}

# Nucleo: sem estas tres o sistema nao cumpre o que promete, entao sao elas
# que definem se o modelo esta "pronto".
PPE_CORE_CLASSES = ("helmet", "vest", "gloves")
# Opcionais: o Vyra (modelo padrao) detecta Goggles e Mask; safety_shoe fica
# como "unsupported" ate entrar um peso que a tenha. Um modelo so com o
# nucleo continua PRONTO — marcar estas como obrigatorias faria todo peso
# de 3 classes ja em uso reportar "modelo parcial" sem nada ter piorado.
PPE_OPTIONAL_CLASSES = ("glasses", "mask", "safety_shoe")
PPE_REQUIRED_CLASSES = PPE_CORE_CLASSES + PPE_OPTIONAL_CLASSES


class YoloPPEDetector:
    def __init__(
        self,
        model_path: str,
        confidence: float = 0.35,
        device: str | None = None,
        classes: list[int] | None = None,
        max_detections: int = 100,
        require_person: bool = True,
    ) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self.device = device
        self.classes = classes
        self.max_detections = max(1, int(max_detections))
        # ponytail: modelos dedicados a EPI (sem classe "person") não devem ser
        # marcados como "não prontos" por não terem pessoa — quem detecta pessoa
        # é outro YoloPPEDetector (ver MonitorService.person_detector).
        self.require_person = require_person
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
        try:
            results = self.model.predict(
                source=frame,
                conf=self.confidence,
                device=self.device,
                classes=self.classes,
                verbose=False,
                max_det=self.max_detections,
            )
        except Exception as exc:  # noqa: BLE001
            # Modelo ausente/corrompido não pode derrubar o frame inteiro —
            # sem isso, uma câmera nova (que nasce com "ppe" ligado por
            # padrão) nunca produz nenhum frame até alguém configurar
            # PPE_MODEL_PATH, mesmo a captura de vídeo em si funcionando.
            # diagnostics() já expõe esse erro (ppe_ready=False + warning);
            # aqui só evita propagar e travar o restante do pipeline.
            self._last_diagnostics = self._build_diagnostics(names={}, error=str(exc))
            self._log_model_warning_once(self._last_diagnostics)
            return []
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
        # Prontidao olha so o nucleo: um modelo com helmet/vest/gloves esta
        # pronto mesmo sem oculos/mascara/calcado.
        core_ok = all(supported_ppe[key] for key in PPE_CORE_CLASSES)
        ready = core_ok and (has_person if self.require_person else True)
        warning = None
        if error:
            warning = f"Modelo YOLO indisponível: {error}"
        elif not any(supported_ppe.values()):
            warning = (
                "O modelo YOLO carregado não possui classes de EPI. "
                "Configure PPE_MODEL_PATH com pesos treinados para helmet/vest/gloves."
            )
        elif not ready:
            missing = [key for key in PPE_CORE_CLASSES if not supported_ppe[key]]
            if self.require_person and not has_person:
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
