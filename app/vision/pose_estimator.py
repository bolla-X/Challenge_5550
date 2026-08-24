from __future__ import annotations

import logging
from functools import cached_property

import cv2
import numpy as np

from app.vision.schemas import BoundingBox, PoseLandmark, PoseResult

logger = logging.getLogger(__name__)

# Margem em volta da caixa da pessoa antes de recortar. O MediaPipe erra mais
# quando o corpo encosta na borda da imagem — um respiro melhora bastante a
# deteccao de ombro/quadril, que e o que as regras de queda e postura usam.
CROP_PADDING = 0.12
# Recorte menor que isto nao tem pixel suficiente para uma pose confiavel.
MIN_CROP_SIDE = 48


class MediaPipePoseEstimator:
    """Pose via MediaPipe, em dois modos.

    `estimate()` roda no frame INTEIRO com tracking temporal ligado
    (`static_image_mode=False`) — e o caminho de sempre, usado como sinal
    global quando nao ha caixa de pessoa.

    `estimate_for_people()` roda um recorte POR PESSOA, com uma instancia
    separada em `static_image_mode=True`. Duas razoes para nao reaproveitar a
    instancia global aqui:

    - o modo com tracking guarda estado entre chamadas; alimenta-lo com
      recortes de pessoas diferentes, alternadamente, corrompe a associacao;
    - sem tracking, cada chamada e independente, que e exatamente o que
      queremos quando a identidade ja vem do PersonTracker.

    O recorte usa `model_complexity=0` (lite): sao N inferencias por frame em
    vez de uma, entao o custo por chamada importa mais que o ganho de precisao
    do modelo medio numa imagem que ja esta enquadrada na pessoa.
    """

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
        logger.info("loading_mediapipe_pose", extra={"mode": "video"})
        return self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )

    @cached_property
    def _pose_crop(self):
        logger.info("loading_mediapipe_pose", extra={"mode": "static_crop"})
        return self._mp_pose.Pose(
            static_image_mode=True,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=self.min_detection_confidence,
        )

    # ------------------------------------------------------------- global ---
    def estimate(self, frame: np.ndarray) -> PoseResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        return PoseResult(landmarks=self._landmarks_from(result))

    # --------------------------------------------------------- por pessoa ---
    def estimate_for_people(
        self,
        frame: np.ndarray,
        people: list[tuple[str, int | None, BoundingBox]],
        *,
        max_people: int = 4,
    ) -> list[PoseResult]:
        """Uma pose por pessoa. `people` traz (person_id, track_id, caixa).

        Pessoas sem pose detectada simplesmente nao aparecem no resultado — o
        chamador nao deve assumir correspondencia 1:1 com a entrada.
        """
        height, width = frame.shape[:2]
        resultados: list[PoseResult] = []

        for person_id, track_id, box in people[: max(1, max_people)]:
            recorte = self._crop(frame, box)
            if recorte is None:
                continue
            imagem, offset_x, offset_y, crop_w, crop_h = recorte

            result = self._pose_crop.process(cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB))
            landmarks = self._landmarks_from(result)
            if not landmarks:
                continue

            # Volta pro espaco normalizado do FRAME: quem consome (anotador,
            # frontend, regras) nao precisa saber que houve recorte.
            remapeados = [
                PoseLandmark(
                    name=item.name,
                    x=(offset_x + item.x * crop_w) / max(1, width),
                    y=(offset_y + item.y * crop_h) / max(1, height),
                    z=item.z,
                    visibility=item.visibility,
                )
                for item in landmarks
            ]
            resultados.append(PoseResult(landmarks=remapeados, person_id=person_id, track_id=track_id))

        return resultados

    def _crop(self, frame: np.ndarray, box: BoundingBox):
        height, width = frame.shape[:2]
        pad_x = int(box.width * CROP_PADDING)
        pad_y = int(box.height * CROP_PADDING)
        x1 = max(0, box.x1 - pad_x)
        y1 = max(0, box.y1 - pad_y)
        x2 = min(width, box.x2 + pad_x)
        y2 = min(height, box.y2 + pad_y)
        if (x2 - x1) < MIN_CROP_SIDE or (y2 - y1) < MIN_CROP_SIDE:
            return None
        return frame[y1:y2, x1:x2], x1, y1, x2 - x1, y2 - y1

    # ------------------------------------------------------------ comum -----
    def _landmarks_from(self, result) -> list[PoseLandmark]:
        if not result or not getattr(result, "pose_landmarks", None):
            return []
        enum_items = list(self._mp_pose.PoseLandmark)
        landmarks: list[PoseLandmark] = []
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
        return landmarks
