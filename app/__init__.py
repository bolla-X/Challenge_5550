from __future__ import annotations

import logging

from flask import Flask, jsonify

from app.api.alerts import alerts_bp
from app.api.cameras import cameras_bp
from app.api.diagnostics import runtime_bp
from app.api.features import features_bp
from app.api.monitor import monitor_bp
from app.api.risk import risk_bp
from app.api.status import status_bp
from app.api.stream import stream_bp
from app.config import Config
from app.extensions import db, migrate, socketio
from app.models import Alert  # noqa: F401  (registra os modelos no metadata)
from app.services.feature_manager import FeatureManager
from app.services.monitor_service import CameraNotFoundError, MonitorService
from app.utils.logging_config import configure_logging


def create_app(config_class: type[Config] = Config) -> Flask:
    configure_logging()

    app = Flask(__name__, static_folder="static")
    app.config.from_object(config_class)

    # SECRET_KEY padrão assina sessão/cookie com um valor que está no código
    # aberto. Em dev é conveniente; fora dele é falha de segurança, então grita
    # alto no log em vez de passar despercebido.
    if not app.config.get("TESTING") and app.config["SECRET_KEY"] == "dev-secret-change-me":
        logging.getLogger(__name__).warning(
            "insecure_secret_key",
            extra={"hint": "Defina SECRET_KEY no .env antes de expor esta aplicação."},
        )

    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS", "*"),
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        logger=False,
        engineio_logger=False,
    )

    feature_manager = FeatureManager.from_config(app.config)
    monitor_service = MonitorService(app, socketio, feature_manager)

    app.extensions["feature_manager"] = feature_manager
    app.extensions["monitor_service"] = monitor_service

    app.register_blueprint(status_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(features_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(runtime_bp)
    app.register_blueprint(risk_bp)

    # Cobre toda rota LEGADA que opera sobre "a câmera padrão" (/start,
    # /stop, /status, /preflight, /settings, /overlay, /risk-area,
    # /analysis/latest) quando não existe nenhuma câmera cadastrada ainda —
    # em vez de deixar cada rota individual lidar com isso, um handler só.
    # (/video_feed é streaming e trata isso dentro do próprio generator,
    # ver app/api/stream.py — um erro aqui não alcançaria o cliente depois
    # que a resposta já começou a ser enviada.)
    @app.errorhandler(CameraNotFoundError)
    def _handle_no_camera(exc: CameraNotFoundError):
        return jsonify({"error": str(exc), "hint": "Cadastre e inicie uma câmera em /api/cameras antes de usar esta rota."}), 404

    if app.config.get("AUTO_CREATE_TABLES", True):
        with app.app_context():
            db.create_all()
            # Sem seed automático de propósito — o usuário cadastra as
            # câmeras dele pela tela/API, nada fictício nasce sozinho.
            monitor_service.load_cameras_from_db()

    return app
