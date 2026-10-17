"""Primeiro acesso do supervisor: estado do assistente, marcar/pular/refazer/concluir.

Só o Supervisor (a rota de contas, uma das ferramentas do assistente, já é dele).
Técnico e Operador recebem 403; sem sessão, 401. `sempre=True`: mesmo com a
autenticação desligada a rota exige sessão, porque grava com o nome de quem marcou.

O blueprint NÃO é registrado em `create_app` por este módulo: quem liga é
`app/__init__.py` (`app.register_blueprint(onboarding_bp)`).
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_SUPERVISOR
from app.services import onboarding as servico
from app.utils.auth import current_user, require_role

onboarding_bp = Blueprint("onboarding", __name__)


def _estado():
    return jsonify(servico.montar_estado(config=current_app.config, instance_path=current_app.instance_path))


def _autor() -> str:
    usuario = current_user()
    return usuario.email if usuario is not None else "sistema"


@onboarding_bp.get("/api/onboarding")
@require_role(ROLE_SUPERVISOR, sempre=True)
def ler_onboarding():
    return _estado()


@onboarding_bp.put("/api/onboarding/<passo>")
@require_role(ROLE_SUPERVISOR, sempre=True)
def definir_passo(passo: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": 'Envie {"estado": "feito" | "pulado" | "pendente"}.'}), 400
    try:
        servico.definir_estado(passo, str(payload.get("estado", "")), por=_autor())
    except servico.PassoDesconhecido as exc:
        return jsonify({"error": str(exc), "code": "passo_desconhecido"}), 404
    except servico.EstadoInvalido as exc:
        return jsonify({"error": str(exc), "code": "estado_invalido"}), 400
    return _estado()


@onboarding_bp.post("/api/onboarding/refazer")
@require_role(ROLE_SUPERVISOR, sempre=True)
def refazer_onboarding():
    servico.refazer(por=_autor())
    return _estado()


@onboarding_bp.post("/api/onboarding/concluir")
@require_role(ROLE_SUPERVISOR, sempre=True)
def concluir_onboarding():
    servico.concluir(por=_autor())
    return _estado()
