from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class RiskAreaConfig:
    enabled: bool
    polygon: list[tuple[float, float]]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///visionepi-dev.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_TABLES = env_bool("AUTO_CREATE_TABLES", True)

    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "0")
    FRAME_WIDTH = env_int("FRAME_WIDTH", 960)
    FRAME_HEIGHT = env_int("FRAME_HEIGHT", 540)
    TARGET_FPS = env_int("TARGET_FPS", 12)
    JPEG_QUALITY = env_int("JPEG_QUALITY", 80)

    PPE_MODEL_PATH = os.getenv("PPE_MODEL_PATH", "models/vyra_ppe.pt")
    # Modelo dedicado a detectar "person" (classe 0 COCO). Só é necessário quando
    # PPE_MODEL_PATH aponta pra um modelo de EPI sem classe "person" própria
    # (ex: epi_pretrained.pt). O Vyra já traz "Person" (classe 11), então roda
    # desligado por padrão — ver MULTI_PERSON_DETECTION abaixo.
    PERSON_MODEL_PATH = os.getenv("PERSON_MODEL_PATH", "yolov8n.pt")
    YOLO_CONFIDENCE = env_float("YOLO_CONFIDENCE", 0.35)
    YOLO_DEVICE = os.getenv("YOLO_DEVICE", None)
    YOLO_CLASSES = os.getenv("YOLO_CLASSES", "")
    YOLO_MAX_DETECTIONS = env_int("YOLO_MAX_DETECTIONS", 100)
    MULTI_PERSON_DETECTION = env_bool("MULTI_PERSON_DETECTION", False)

    POSE_MIN_DETECTION_CONFIDENCE = env_float("POSE_MIN_DETECTION_CONFIDENCE", 0.5)
    POSE_MIN_TRACKING_CONFIDENCE = env_float("POSE_MIN_TRACKING_CONFIDENCE", 0.5)

    ALERT_COOLDOWN_SECONDS = env_int("ALERT_COOLDOWN_SECONDS", 0)
    ALERT_CREATE_AFTER_FRAMES = env_int("ALERT_CREATE_AFTER_FRAMES", 3)
    ALERT_RESOLVE_AFTER_FRAMES = env_int("ALERT_RESOLVE_AFTER_FRAMES", 5)
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv("SOCKETIO_CORS_ALLOWED_ORIGINS", "*")
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")

    CLEANUP_ON_MONITOR_START = env_bool("CLEANUP_ON_MONITOR_START", True)
    CLEANUP_DIRECTORIES = os.getenv("CLEANUP_DIRECTORIES", "runtime/snapshots,runtime/frames,runtime/tmp")
    SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "runtime/snapshots")
    SNAPSHOT_ENABLED = env_bool("SNAPSHOT_ENABLED", True)
    SNAPSHOT_JPEG_QUALITY = env_int("SNAPSHOT_JPEG_QUALITY", 86)
    TIMELINE_LIMIT = env_int("TIMELINE_LIMIT", 80)
    RISK_AREA_NAME = os.getenv("RISK_AREA_NAME", "Área de risco")

    OVERLAY_SHOW_BOXES = env_bool("OVERLAY_SHOW_BOXES", True)
    OVERLAY_SHOW_LABELS = env_bool("OVERLAY_SHOW_LABELS", True)
    OVERLAY_SHOW_CONFIDENCE = env_bool("OVERLAY_SHOW_CONFIDENCE", True)
    OVERLAY_SHOW_POSE = env_bool("OVERLAY_SHOW_POSE", True)
    OVERLAY_SHOW_RISK_AREA = env_bool("OVERLAY_SHOW_RISK_AREA", True)

    DEFAULT_FEATURES = os.getenv(
        "DEFAULT_FEATURES",
        "ppe,helmet,vest,gloves,glasses,pose,falls,posture,risk_area",
    )
    RISK_AREA_POLYGON = os.getenv("RISK_AREA_POLYGON", "0.70,0.10;0.98,0.10;0.98,0.95;0.70,0.95")

    @staticmethod
    def parse_video_source(value: str | int) -> str | int:
        if isinstance(value, int):
            return value
        return int(value) if str(value).isdigit() else value

    @classmethod
    def get_video_source(cls) -> str | int:
        return cls.parse_video_source(cls.VIDEO_SOURCE)

    @classmethod
    def get_enabled_feature_keys(cls) -> set[str]:
        return {item.strip() for item in cls.DEFAULT_FEATURES.split(",") if item.strip()}

    @classmethod
    def get_yolo_classes(cls) -> list[int] | None:
        raw = cls.YOLO_CLASSES.strip()
        if not raw:
            return None
        classes: list[int] = []
        for item in raw.split(","):
            item = item.strip()
            if item:
                classes.append(int(item))
        return classes

    @classmethod
    def get_risk_area_config(cls) -> RiskAreaConfig:
        polygon: list[tuple[float, float]] = []
        for pair in cls.RISK_AREA_POLYGON.split(";"):
            x, y = pair.split(",")
            polygon.append((float(x), float(y)))
        return RiskAreaConfig(enabled=True, polygon=polygon)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AUTO_CREATE_TABLES = False
    DEFAULT_FEATURES = "ppe,helmet,vest,gloves,pose,falls,posture,risk_area"
