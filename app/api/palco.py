"""Modo Apresentação (X6): roteiro, cena atual e controle pelo celular.

`/api/palco/estado` e `/api/palco/ir` aceitam sessão de técnico/supervisor OU
o token do QR (`?t=`), porque o celular não tem login. O token só muda a cena
do palco — não dá acesso a vídeo, alerta nem dado nenhum.
"""

from __future__ import annotations

import hmac
import threading

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_TECHNICAL, Camera
from app.services.palco import ROTEIRO, Palco, camera_da_cena
from app.utils.auth import current_user, login_required, require_role

palco_bp = Blueprint("palco", __name__)


def _palco() -> Palco:
    palco = current_app.extensions.get("palco")
    if palco is None:
        palco = current_app.extensions["palco"] = Palco()
    return palco


def _negado():
    """None = pode; senão a resposta de erro (401 sem sessão nem token, 403 token/papel errado)."""
    token = request.args.get("t") or (request.get_json(silent=True) or {}).get("t") or ""
    if token:
        return None if hmac.compare_digest(str(token), _palco().token) else (jsonify({"error": "token inválido"}), 403)
    if not current_app.config.get("AUTH_REQUIRED", True):
        return None
    usuario = current_user()
    if usuario is None:
        return jsonify({"error": "Autenticação necessária.", "code": "unauthenticated"}), 401
    return None if usuario.has_role(ROLE_TECHNICAL) else (jsonify({"error": "Seu perfil não permite esta ação."}), 403)


def _cameras_por_nome() -> dict[str, int]:
    return {c.name: c.id for c in Camera.query.all()}


@palco_bp.get("/api/palco/roteiro")
@login_required
def roteiro():
    por_nome = _cameras_por_nome()
    cenas = [cena | {"camera_id": camera_da_cena(cena, por_nome)} for cena in ROTEIRO]
    return jsonify({"cenas": cenas, "estado": _palco().publico()})


@palco_bp.get("/api/palco/estado")
def estado():
    negado = _negado()
    if negado:
        return negado
    return jsonify(_palco().publico())


def _preparar(app, cena: dict) -> None:
    """Gatilho determinístico da cena: a gravação recomeça do início."""
    if not cena.get("reiniciar"):
        return
    with app.app_context():
        camera_id = camera_da_cena(cena, _cameras_por_nome())
        if camera_id is None:
            return
        monitor = app.extensions["monitor_service"]
        try:
            worker = monitor.worker_da_camera(camera_id)
        except LookupError:
            return
        worker.stop()
        worker.start()


@palco_bp.post("/api/palco/ir")
def ir():
    negado = _negado()
    if negado:
        return negado
    corpo = request.get_json(silent=True) or {}
    palco = _palco()
    anterior = palco.estado.cena
    try:
        novo = palco.ir(acao=str(corpo.get("acao", "")), indice=corpo.get("indice"))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    if novo.cena != anterior:
        # Em thread: reiniciar a gravação leva ~1–2 s e o celular não espera.
        threading.Thread(target=_preparar, args=(current_app._get_current_object(), ROTEIRO[novo.cena]), daemon=True).start()
    return jsonify(palco.publico())


@palco_bp.get("/api/palco/controle")
@require_role(ROLE_TECHNICAL)
def controle():
    """URL do controle (para o QR da tela do palco)."""
    from app.api.celular import _ip_da_lan

    palco = _palco()
    caminho = f"/palco/controle?t={palco.token}"
    porta = request.host.rsplit(":", 1)[-1] if ":" in request.host else ("443" if request.is_secure else "80")
    ip = _ip_da_lan()
    esquema = "https" if request.is_secure else "http"
    return jsonify({
        "caminho": caminho,
        "url_lan": f"{esquema}://{ip}:{porta}{caminho}" if ip else None,
        "https": request.is_secure,
        "aviso": None if request.is_secure else
        "Servidor em HTTP só nesta máquina: para o celular alcançar, rode python run.py --demo --https.",
    })
