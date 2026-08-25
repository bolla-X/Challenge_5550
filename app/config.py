from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

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
    # Valores que aparecem NO PROPRIO REPOSITORIO — qualquer um que leia o
    # projeto os conhece. Checar so o default do codigo nao bastava: o
    # .env.example (que o README manda copiar) entrega outro literal, e a
    # aplicacao subia com chave publica.
    SECRET_KEYS_PUBLICAS = frozenset({"dev-secret-change-me", "change-me", "changeme", "secret", ""})
    # Abaixo disto a chave e curta demais pra assinatura de sessao.
    SECRET_KEY_MIN_LENGTH = 32

    # Porta única, lida daqui por run.py, Dockerfile, docker-compose e pelo
    # proxy do Vite. Antes o run.py escutava 5003 enquanto Dockerfile/compose/
    # README falavam em 5000 — o container subia com a porta publicada errada
    # e ninguém alcançava a aplicação.
    # Autenticacao. Desligar so faz sentido em teste automatizado; num
    # ambiente com camera apontada pra pessoas, exigir login e o padrao.
    AUTH_REQUIRED = env_bool("AUTH_REQUIRED", True)
    # Sessao assinada com SECRET_KEY, em cookie HttpOnly (o JS da pagina
    # nao le, entao XSS nao rouba a sessao).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # LIGUE em producao (exige HTTPS). Fica desligado por padrao porque
    # cookie Secure nao viaja em http://localhost e quebraria o dev.
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=env_int("SESSION_HOURS", 12))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = env_int("PORT", 5000)
    # Werkzeug em modo debug expõe console interativo = execução remota de
    # código. Nunca liga sozinho: só com FLASK_DEBUG explícito no ambiente.
    DEBUG = env_bool("FLASK_DEBUG", False)
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
    # Lado maior da imagem que entra na rede. O ultralytics usa 640 quando não
    # se diz nada, e é o custo dominante do pipeline: medido nesta máquina
    # (CPU, sem CUDA), o YOLOv8m leva 327 ms/frame a 640 contra 135 ms a 320 —
    # 2,4x. Abaixar melhora FPS e piora objetos pequenos/distantes, então é
    # escolha de operação, não constante: fica no .env.
    YOLO_IMGSZ = env_int("YOLO_IMGSZ", 640)
    # Roda a detecção 1 frame a cada N; os intermediários reaproveitam as
    # últimas caixas. Serve para desacoplar a fluidez do vídeo da velocidade da
    # inferência — com N=1 o comportamento é exatamente o de antes.
    DETECTION_EVERY_N_FRAMES = env_int("DETECTION_EVERY_N_FRAMES", 1)
    # Segundos entre gravações de um alerta que continua ativo. Cada gravação
    # é um commit (9,2 ms aqui) feito DENTRO do loop de captura, e antes
    # acontecia por alerta a cada frame — o vídeo travava justamente quando
    # havia infração. Criar e resolver seguem imediatos. 0 volta ao antigo.
    ALERT_TOUCH_INTERVAL_SECONDS = env_float("ALERT_TOUCH_INTERVAL_SECONDS", 2.0)
    # Quantas vezes por segundo a telemetria (analysis/compliance) vai pro
    # navegador. O VÍDEO não passa por aqui — ele é MJPEG com as caixas já
    # desenhadas — então baixar isto não deixa a imagem menos fluida; evita
    # que ~26 KB por evento por câmera afoguem o browser a 24 FPS.
    TELEMETRY_HZ = env_float("TELEMETRY_HZ", 8.0)
    # Diagnostico: a cada N frames, loga quanto cada etapa do loop custou.
    # 0 = desligado (padrao). Use quando o video estiver travado pra ver ONDE
    # o tempo vai, em vez de adivinhar pelo FPS medio.
    PROFILE_FRAMES = env_int("PROFILE_FRAMES", 0)
    MULTI_PERSON_DETECTION = env_bool("MULTI_PERSON_DETECTION", False)

    # Uma pose POR PESSOA (recorte da caixa) em vez de uma pose global do
    # frame. E o que permite atribuir queda/postura a um individuo. Custa N
    # inferencias por frame, entao POSE_MAX_PEOPLE limita o pior caso.
    POSE_PER_PERSON = env_bool("POSE_PER_PERSON", True)
    POSE_MAX_PEOPLE = env_int("POSE_MAX_PEOPLE", 4)
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
        "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,pose,falls,posture,risk_area",
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
    # Cada teste foca no proprio assunto; exigir login em todos so adicionaria
    # ruido. Quem exercita a autenticacao de verdade e tests/test_auth.py, que
    # sobe com AUTH_REQUIRED=True e verifica rota por rota — inclusive uma
    # varredura que falha se aparecer rota nova desprotegida.
    AUTH_REQUIRED = False
    DEFAULT_FEATURES = "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,pose,falls,posture,risk_area"


class AuthTestConfig(TestConfig):
    """TestConfig com autenticacao LIGADA."""

    AUTH_REQUIRED = True
    SECRET_KEY = "chave-de-teste-nao-usada-em-lugar-nenhum"
