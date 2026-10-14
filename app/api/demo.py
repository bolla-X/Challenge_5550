"""`POST /api/demo/reset` — existe só com DEMO_MODE (ver app/demo.py).

Autoriza o token local de `instance/demo/token` (é o que o `flask demo reset`
manda) ou uma sessão de supervisor.
"""

from __future__ import annotations

import secrets

from flask import Blueprint, current_app, jsonify, request

from app.demo import TOKEN, resetar_no_servidor
from app.models import ROLE_SUPERVISOR
from app.utils.auth import current_user

demo_bp = Blueprint("demo", __name__)


def _autorizado() -> bool:
    enviado = request.headers.get("X-Demo-Token", "")
    if enviado and TOKEN.exists() and secrets.compare_digest(enviado, TOKEN.read_text(encoding="utf-8").strip()):
        return True
    usuario = current_user()
    return usuario is not None and usuario.active and usuario.role == ROLE_SUPERVISOR


@demo_bp.post("/api/demo/reset")
def reset():
    if not _autorizado():
        return jsonify({"error": "só o supervisor (ou o terminal da demo) reinicia a demo"}), 403
    return jsonify(resetar_no_servidor(current_app._get_current_object()))
