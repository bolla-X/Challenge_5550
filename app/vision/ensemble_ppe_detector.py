from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.vision.schemas import Detection
from app.vision.yolo_ppe_detector import PPE_CORE_CLASSES, YoloPPEDetector

logger = logging.getLogger(__name__)

# Duas deteccoes com o MESMO label e IoU acima disto sao a mesma coisa vista
# por dois modelos: mantem a de maior confianca e descarta a outra. Abaixo
# disto sao objetos distintos (duas luvas, duas pessoas) e ambas ficam.
_DEDUPE_IOU = 0.55


class EnsemblePPEDetector:
    """Roda varios `YoloPPEDetector` no mesmo frame e funde o resultado.

    Existe porque a arquitetura tem so dois slots de modelo (EPI + pessoa) e
    nenhum peso unico cobre bem todas as classes: o Vyra acerta capacete/colete
    e erra oculos/mascara/luva; um modelo dedicado a esses tres cobre a lacuna.
    Expoe a MESMA interface que o `CameraWorker` usa de um `YoloPPEDetector`
    (`detect`, `diagnostics`, `supported_ppe_classes`, `model_path`,
    `confidence`, `max_detections`), entao o worker nao sabe que sao varios.

    Custo: a inferencia de EPI passa a ser a soma dos modelos. Com o Vyra
    (YOLOv8m) + um YOLOv8n o acrescimo e pequeno; `DETECTION_EVERY_N_FRAMES`
    continua sendo a alavanca pra desacoplar isso da fluidez do video.
    """

    def __init__(self, detectors: list[YoloPPEDetector]) -> None:
        if not detectors:
            raise ValueError("EnsemblePPEDetector precisa de ao menos um detector")
        self._detectors = detectors

    # -- interface consumida pelo CameraWorker --------------------------------

    @property
    def model_path(self) -> str:
        return " + ".join(d.model_path for d in self._detectors)

    @property
    def confidence(self) -> float:
        return float(self._detectors[0].confidence)

    @confidence.setter
    def confidence(self, value: float) -> None:
        for d in self._detectors:
            d.confidence = value

    @property
    def max_detections(self) -> int:
        return int(self._detectors[0].max_detections)

    @max_detections.setter
    def max_detections(self, value: int) -> None:
        for d in self._detectors:
            d.max_detections = value

    def detect(self, frame: np.ndarray) -> list[Detection]:
        todas: list[Detection] = []
        for d in self._detectors:
            todas.extend(d.detect(frame))
        return self._fundir(todas)

    def supported_ppe_classes(self) -> set[str]:
        uniao: set[str] = set()
        for d in self._detectors:
            uniao |= d.supported_ppe_classes()
        return uniao

    def diagnostics(self) -> dict[str, Any]:
        por_modelo = [dict(d.diagnostics()) for d in self._detectors]

        supported_ppe: dict[str, bool] = {}
        for diag in por_modelo:
            for chave, ok in (diag.get("supported_ppe") or {}).items():
                supported_ppe[chave] = supported_ppe.get(chave, False) or bool(ok)

        person_supported = any(d.get("person_supported") for d in por_modelo)
        # Pronto se ALGUM modelo cobre o nucleo helmet/vest/gloves — juntos eles
        # podem cobrir o nucleo mesmo que nenhum o cubra sozinho.
        core_ok = all(supported_ppe.get(k) for k in PPE_CORE_CLASSES)

        erros = [d.get("error") for d in por_modelo if d.get("error")]
        avisos = [d.get("warning") for d in por_modelo if d.get("warning")]
        warning = None
        if erros and len(erros) == len(por_modelo):
            warning = f"Todos os modelos de EPI indisponiveis: {'; '.join(erros)}"
        elif not any(supported_ppe.values()):
            warning = "Nenhum modelo do ensemble possui classes de EPI."
        elif not core_ok:
            faltam = [k for k in PPE_CORE_CLASSES if not supported_ppe.get(k)]
            warning = f"Ensemble parcial para EPI. Classes ausentes em todos: {', '.join(faltam)}."
        elif avisos:
            warning = " ".join(avisos)

        return {
            "model_path": self.model_path,
            "confidence": self.confidence,
            "device": por_modelo[0].get("device"),
            "class_filter": [d.get("class_filter") for d in por_modelo],
            "max_detections": self.max_detections,
            "imgsz": por_modelo[0].get("imgsz"),
            "raw_class_count": sum(int(d.get("raw_class_count") or 0) for d in por_modelo),
            "classes": [c for d in por_modelo for c in (d.get("classes") or [])],
            "supported_ppe": supported_ppe,
            "person_supported": person_supported,
            "ppe_ready": core_ok and (person_supported if any(
                getattr(d, "require_person", False) for d in self._detectors
            ) else True),
            "warning": warning,
            "error": erros[0] if erros else None,
            "ensemble": por_modelo,
        }

    # -- fusao --------------------------------------------------------------

    @staticmethod
    def _fundir(deteccoes: list[Detection]) -> list[Detection]:
        # Maior confianca primeiro: a primeira caixa de cada label vence e
        # suprime as sobrepostas que vierem depois.
        ordenadas = sorted(deteccoes, key=lambda d: d.confidence, reverse=True)
        mantidas: list[Detection] = []
        for cand in ordenadas:
            duplicada = any(
                m.label == cand.label and m.box.iou(cand.box) >= _DEDUPE_IOU
                for m in mantidas
            )
            if not duplicada:
                mantidas.append(cand)
        return mantidas
