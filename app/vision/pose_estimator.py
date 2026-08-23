from __future__ import annotations

import logging
from functools import cached_property

import cv2
import numpy as np

from app.vision.schemas import PoseLandmark, PoseResult

logger = logging.getLogger(__name__)


class MediaPipePoseEstimator:
    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5) -> None:
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence

    @cached_property
    def _mp_pose(self):
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError("Pacote mediapipe não instalado. Rode pip install -r requirements.txt") from exc
        return mp.solutions.pose

    @cached_property
    def _pose(self):
        logger.info("loading_mediapipe_pose")
        return self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )

    def estimate(self, frame: np.ndarray) -> PoseResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return PoseResult(landmarks=[])

        landmarks: list[PoseLandmark] = []
        enum_items = list(self._mp_pose.PoseLandmark)
        for idx, landmark in enumerate(result.pose_landmarks.landmark):
            name = enum_items[idx].name.lower() if idx < len(enum_items) else f"landmark_{idx}"
            landmarks.append(
                PoseLandmark(
                    name=name,
                    x=float(landmark.x),
                    y=float(landmark.y),
                    z=float(landmark.z),
                    visibility=float(landmark.visibility),
                )
            )
        return PoseResult(landmarks=landmarks)
