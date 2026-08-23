from __future__ import annotations

import logging

from flask import Flask

from app.config import Config
from app.extensions import db
from app.models import Camera

logger = logging.getLogger(__name__)


def _infer_source_type(raw_source: str) -> str:
    """Mesma lógica de reconhecimento que MonitorService/VideoStream já usam
    implicitamente (ver Config.parse_video_source) — só que aqui é pra
    popular o campo `source_type` da UI, puramente informativo."""
    value = str(raw_source).strip()
    if value.isdigit():
        return "USB"
    if value.startswith(("rtsp://", "http://", "https://")):
        return "RTSP"
    return "Arquivo"


def seed_default_camera(app: Flask) -> None:
    """Garante que sempre existe pelo menos 1 câmera cadastrada.

    Roda no boot, dentro do app_context. Só semeia se a tabela estiver
    vazia — em nenhuma outra situação mexe no banco, então rodar o app de
    novo depois que você já tiver criado/editado câmeras não reseta nada.

    A câmera semente usa o VIDEO_SOURCE atual do .env, pra manter o
    comportamento de hoje (single-source) idêntico enquanto o
    CameraWorker multi-fonte ainda não existe — ver Fase A do plano.
    """
    if Camera.query.count() > 0:
        return

    raw_source = str(app.config.get("VIDEO_SOURCE", Config.VIDEO_SOURCE))
    camera = Camera(
        name="Câmera 1",
        location=None,
        source_type=_infer_source_type(raw_source),
        source=raw_source,
        fps=int(app.config.get("TARGET_FPS", 12)),
        enabled=True,
    )
    db.session.add(camera)
    db.session.commit()
    logger.info("camera_seeded", extra={"camera_id": camera.id, "source": raw_source})
