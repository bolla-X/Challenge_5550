from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

# Estava duplicado em api/stream.py e api/cameras.py — mesma função, duas
# cópias. lru_cache porque o frame é constante: o loop de streaming chamava
# isto ~12x por segundo, alocando e recodificando o mesmo JPEG toda vez.


@lru_cache(maxsize=8)
def placeholder_jpeg(message: str) -> bytes:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    cv2.putText(frame, message, (40, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    return buffer.tobytes() if ok else b""
