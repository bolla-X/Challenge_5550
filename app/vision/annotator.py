from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.vision.schemas import Detection, PoseResult


class FrameAnnotator:
    def __init__(self, risk_polygon: list[tuple[float, float]]) -> None:
        self.risk_polygon = risk_polygon

    def annotate(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        pose: PoseResult | None,
        enabled_features: dict[str, bool],
        compliance_state: dict[str, Any] | None = None,
        overlay_options: dict[str, bool] | None = None,
    ) -> np.ndarray:
        output = frame.copy()
        options = overlay_options or {}
        if options.get("risk_area", True):
            self._draw_risk_area(output, enabled_features)
        self._draw_detections(output, detections, options)
        if pose and pose.found and enabled_features.get("pose", False) and options.get("pose", True):
            self._draw_pose_points(output, pose)
        return output

    def _draw_detections(self, frame: np.ndarray, detections: list[Detection], options: dict[str, bool]) -> None:
        show_boxes = options.get("boxes", True)
        show_labels = options.get("labels", True)
        show_confidence = options.get("confidence", True)
        if not show_boxes and not show_labels:
            return
        for det in detections:
            color = self._color_for(det.label)
            if show_boxes:
                cv2.rectangle(frame, (det.box.x1, det.box.y1), (det.box.x2, det.box.y2), color, 2)
            if show_labels:
                text = self._display_label(det.label)
                if show_confidence:
                    text = f"{text} {det.confidence:.2f}"
                cv2.putText(frame, text, (det.box.x1, max(20, det.box.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    def _draw_pose_points(self, frame: np.ndarray, pose: PoseResult) -> None:
        h, w = frame.shape[:2]
        for landmark in pose.landmarks:
            if landmark.visibility < 0.45:
                continue
            cv2.circle(frame, (int(landmark.x * w), int(landmark.y * h)), 3, (255, 255, 255), -1)

    def _draw_risk_area(self, frame: np.ndarray, enabled_features: dict[str, bool]) -> None:
        if not enabled_features.get("risk_area", False):
            return
        h, w = frame.shape[:2]
        points = np.array([[int(x * w), int(y * h)] for x, y in self.risk_polygon], dtype=np.int32)
        if len(points) >= 3:
            cv2.polylines(frame, [points], isClosed=True, color=(0, 165, 255), thickness=2)
            cv2.putText(frame, "AREA DE RISCO", tuple(points[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)

    @staticmethod
    def _display_label(label: str) -> str:
        return {
            "helmet": "capacete",
            "vest": "colete",
            "gloves": "luvas",
            "person": "pessoa",
        }.get(label, label)

    @staticmethod
    def _color_for(label: str) -> tuple[int, int, int]:
        if label == "helmet":
            return (0, 255, 0)
        if label == "vest":
            return (255, 255, 0)
        if label == "gloves":
            return (255, 0, 255)
        if label == "person":
            return (255, 128, 0)
        return (255, 255, 255)
