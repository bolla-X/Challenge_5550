from __future__ import annotations

import logging
import threading
from time import sleep
from typing import Any

import cv2

logger = logging.getLogger(__name__)


class VideoStreamError(RuntimeError):
    pass


class VideoStream:
    def __init__(self, source: str | int, width: int, height: int) -> None:
        self.source = source
        self.width = width
        self.height = height
        self._capture: cv2.VideoCapture | None = None
        self._lock = threading.RLock()
        self._latest_frame = None

    def open(self) -> None:
        with self._lock:
            if self._capture and self._capture.isOpened():
                return
            self._capture = cv2.VideoCapture(self.source)
            if not self._capture.isOpened():
                raise VideoStreamError(f"Não foi possível abrir a fonte de vídeo: {self.source}")
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            logger.info("video_stream_opened", extra={"source": str(self.source)})

    def read(self) -> tuple[bool, Any]:
        with self._lock:
            if not self._capture or not self._capture.isOpened():
                self.open()
            assert self._capture is not None
            ok, frame = self._capture.read()
            if ok:
                self._latest_frame = frame.copy()
            return ok, frame

    def latest_frame(self) -> Any:
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def release(self) -> None:
        with self._lock:
            if self._capture:
                self._capture.release()
                self._capture = None
                logger.info("video_stream_released", extra={"source": str(self.source)})

    def warmup(self, attempts: int = 5) -> bool:
        self.open()
        for _ in range(attempts):
            ok, _ = self.read()
            if ok:
                return True
            sleep(0.1)
        return False
