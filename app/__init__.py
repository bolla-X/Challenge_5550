from __future__ import annotations

import logging

from flask import Flask, jsonify

from app.api.alerts import alerts_bp
from app.api.auth import auth_bp
from app.api.cameras import cameras_bp
from app.api.diagnostics import runtime_bp
from app.api.features import features_bp
from app.api.monitor import monitor_bp
from app.api.risk import risk_bp
from app.api.status import status_bp
from app.api.stream import stream_bp
from app.cli import register_cli
from app.config import Config
from app.extensions import db, migrate, socketio
from app.models import Alert, User  # noqa: F401  (registra os modelos no metadata)
from app.services.feature_manager import FeatureManager
from app.services.monitor_service import CameraNotFoundError, MonitorService
from app.utils.auth import current_user
from app.utils.logging_config import configure_logging


def create_app(config_class: type[Config] = Config) -> Flask:
    configure_logging()

    app = Flask(__name__, static_folder="static")
    app.config.from_object(config_class)

    # A sessão de login é assinada com SECRET_KEY. Com o valor padrão — que
    # está no código aberto — qualquer pessoa forja o cookie de um supervisor.
    # Por isso aqui é ERRO, não aviso: só passa em teste ou com FLASK_DEBUG.
    if app.config["SECRET_KEY"] == "dev-secret-change-me" and app.config.get("AUTH_REQUIRED", True):
        if not app.config.get("TESTING") and not app.config.get("DEBUG"):
            raise RuntimeError(
                "SECRET_KEY está no valor padrão do repositório. Com autenticação ligada isso "
                "permite forjar a sessão de qualquer usuário. Defina SECRET_KEY no .env "
                "(ex.: python -c \"import secrets; print(secrets.token_hex(32))\")."
            )
        logging.getLogger(__name__).warning(
            "insecure_secret_key",
            extra={"hint": "SECRET_KEY padrão — aceitável só em desenvolvimento."},
        )
    if app.config.get("AUTH_REQUIRED", True) and not app.config.get("SESSION_COOKIE_SECURE") and not app.config.get("DEBUG"):
        logging.getLogger(__name__).warning(
            "session_cookie_not_secure",
            extra={"hint": "Atrás de HTTPS, defina SESSION_COOKIE_SECURE=true no .env."},
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

    app.register_blueprint(auth_bp)
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

    # WebSocket tambem exige sessao: sem isto, todo o feed de analise, alertas
    # e compliance vazaria pra qualquer um que abrisse um socket na porta —
    # protegendo so o REST, a porta dos fundos ficaria escancarada.
    @socketio.on("connect")
    def _authorize_socket(auth=None):  # noqa: ARG001  (assinatura do Flask-SocketIO)
        if not app.config.get("AUTH_REQUIRED", True):
            return True
        if current_user() is None:
            logging.getLogger(__name__).warning("socket_rejected_unauthenticated")
            return False
        return True

    register_cli(app)

    if app.config.get("AUTO_CREATE_TABLES", True):
        with app.app_context():
            db.create_all()
            # Sem seed automático de propósito — o usuário cadastra as
            # câmeras dele pela tela/API, nada fictício nasce sozinho.
            monitor_service.load_cameras_from_db()

    return app
