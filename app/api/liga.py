"""Liga de Setores, missões (X8) e Retrospectiva (X7)."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import ROLE_SUPERVISOR, Missao
from app.services import liga, retrospectiva
from app.utils.auth import login_required, require_role

liga_bp = Blueprint("liga", __name__)


@liga_bp.get("/api/liga")
@login_required
def estado_da_liga():
    return jsonify(liga.estado(turnos=current_app.config.get("TURNOS", "06:00-14:00,14:00-22:00,22:00-06:00")))


@liga_bp.get("/api/retrospectiva")
@login_required
def retrospectiva_do_periodo():
    periodo = request.args.get("periodo", "turno")
    if periodo not in ("turno", "semana"):
        return jsonify({"error": "periodo deve ser turno ou semana"}), 400
    return jsonify(retrospectiva.montar(periodo, turnos=current_app.config.get("TURNOS", "06:00-14:00,14:00-22:00,22:00-06:00")))


def _validar(corpo: dict) -> dict:
    tipo = str(corpo.get("tipo", ""))
    if tipo not in liga.TIPOS_DE_MISSAO:
        raise ValueError(f"tipo deve ser um de: {', '.join(liga.TIPOS_DE_MISSAO)}")
    alvo = int(corpo.get("alvo", 0))
    if not 1 <= alvo <= 10000:
        raise ValueError("alvo entre 1 e 10000")
    titulo = str(corpo.get("titulo", "")).strip()[:160]
    if not titulo:
        raise ValueError("título obrigatório")
    ate_hora = corpo.get("ate_hora") or None
    if ate_hora is not None:
        liga._hora(str(ate_hora))
    setor = (str(corpo.get("setor")).strip()[:160] or None) if corpo.get("setor") else None
    return {"tipo": tipo, "alvo": alvo, "titulo": titulo, "ate_hora": ate_hora, "setor": setor}


@liga_bp.post("/api/liga/missoes")
@require_role(ROLE_SUPERVISOR)
def criar_missao():
    try:
        dados = _validar(request.get_json(silent=True) or {})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    missao = Missao(**dados, ativa=True)
    db.session.add(missao)
    db.session.commit()
    return jsonify({"missao": missao.to_dict()}), 201


@liga_bp.delete("/api/liga/missoes/<int:missao_id>")
@require_role(ROLE_SUPERVISOR)
def desativar_missao(missao_id: int):
    missao = db.session.get(Missao, missao_id)
    if missao is None:
        return jsonify({"error": "missão não encontrada"}), 404
    liga.desativar_missao(missao)
    return jsonify({"missao": missao.to_dict()})
