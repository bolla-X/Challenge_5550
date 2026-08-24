from __future__ import annotations

import time

from flask import Blueprint, Response, current_app, jsonify

from app.api.placeholder import placeholder_jpeg

stream_bp = Blueprint("stream", __name__)


@stream_bp.get("/video_feed")
def video_feed():
    monitor = current_app.extensions["monitor_service"]
    target_fps = max(1, current_app.config.get("TARGET_FPS", 12))

    def generate():
        while True:
            # LookupError = nenhuma câmera cadastrada (estado válido: o seed
            # automático foi removido). Sem este try o CameraNotFoundError
            # subia de dentro do generator, onde o errorhandler do app já não
            # alcança — a resposta streaming já começou — e derrubava a
            # conexão com traceback. O comentário em app/__init__.py afirmava
            # que isto era tratado aqui; agora é de fato.
            try:
                jpeg = monitor.latest_jpeg()
            except LookupError:
                jpeg = None
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + (
                jpeg or placeholder_jpeg("VisionEPI: nenhuma camera ativa")
            ) + b"\r\n"
            time.sleep(1 / target_fps)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@stream_bp.get("/analysis/latest")
def latest_analysis():
    monitor = current_app.extensions["monitor_service"]
    try:
        return jsonify(monitor.latest_analysis() or {})
    except LookupError:
        return jsonify({})
