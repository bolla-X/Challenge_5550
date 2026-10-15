"""Celular como câmera (F6): página `/cam`, recepção de quadros e pareamento por QR.

Duas rotas são públicas de propósito — o celular não tem sessão — e ambas são
inofensivas sem o token da câmera:

- `GET /cam`: HTML estático, sem dado nenhum (o token vem na URL e só o JS da
  página o usa);
- `POST /api/celular/<token>/quadro`: só aceita quadro para um token que
  existe, de uma câmera em monitoramento, com tamanho e taxa limitados.

O pareamento (`GET /api/cameras/<id>/celular`) exige técnico.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app.extensions import db
from app.models import ROLE_TECHNICAL, Camera
from app.utils.auth import camera_permitida, erro_fora_do_escopo, require_role
from app.vision.fonte_celular import MAX_BYTES_QUADRO, PREFIXO, fonte_do_token

celular_bp = Blueprint("celular", __name__)

# Teto por token: o celular manda ~5 fps; isto só barra abuso.
QUADROS_POR_S_MAX = 15.0
_ultimo_por_token: dict[str, float] = {}


@celular_bp.get("/cam")
def pagina():
    return send_from_directory(Path(current_app.static_folder), "cam.html", max_age=0)


@celular_bp.post("/api/celular/<token>/quadro")
def receber_quadro(token: str):
    fonte = fonte_do_token(token)
    if fonte is None:
        return jsonify({"error": "token desconhecido ou câmera parada"}), 404
    if (request.content_length or 0) > MAX_BYTES_QUADRO:
        return jsonify({"error": "quadro grande demais"}), 413
    agora = time.monotonic()
    if agora - _ultimo_por_token.get(token, 0.0) < 1.0 / QUADROS_POR_S_MAX:
        return jsonify({"ok": False, "motivo": "taxa"}), 429
    _ultimo_por_token[token] = agora
    if not fonte.receber(request.get_data(cache=False)):
        return jsonify({"error": "não é uma imagem JPEG válida"}), 400
    return jsonify({"ok": True})


def _ip_da_lan() -> str | None:
    """IP desta máquina na rede local (para o QR). `connect` em UDP não envia nada."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


@celular_bp.get("/api/cameras/<int:camera_id>/celular")
@require_role(ROLE_TECHNICAL)
def pareamento(camera_id: int):
    if not camera_permitida(camera_id):
        return erro_fora_do_escopo()
    camera = db.session.get(Camera, camera_id)
    if camera is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    if not str(camera.source or "").startswith(PREFIXO):
        return jsonify({"error": "esta câmera não é do tipo Celular"}), 409
    token = str(camera.source)[len(PREFIXO):]
    porta = request.host.rsplit(":", 1)[-1] if ":" in request.host else ("443" if request.is_secure else "80")
    ip = _ip_da_lan()
    return jsonify({
        "camera_id": camera_id,
        "caminho": f"/cam?t={token}",
        "url_lan": f"https://{ip}:{porta}/cam?t={token}" if ip else None,
        "https": request.is_secure,
        "aviso": None if request.is_secure else
        "Servidor em HTTP: o celular só libera a câmera em HTTPS (rode python run.py --https).",
    })
