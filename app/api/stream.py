from __future__ import annotations

import time

import cv2
import numpy as np
from flask import Blueprint, Response, current_app, jsonify

stream_bp = Blueprint("stream", __name__)


def _placeholder_jpeg(message: str) -> bytes:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    cv2.putText(frame, message, (40, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    return buffer.tobytes() if ok else b""


@stream_bp.get("/video_feed")
def video_feed():
    monitor = current_app.extensions["monitor_service"]
    target_fps = max(1, current_app.config.get("TARGET_FPS", 12))

    def generate():
        while True:
            jpeg = monitor.latest_jpeg() or _placeholder_jpeg("VisionEPI: monitoramento parado ou sem frame")
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(1 / target_fps)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@stream_bp.get("/analysis/latest")
def latest_analysis():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.latest_analysis() or {})
