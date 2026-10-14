"""Cadeia de custódia (X3): verificar a integridade das evidências."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import ROLE_TECHNICAL, ElodeCustodia, Incidente
from app.services.custodia import verificar
from app.utils.auth import camera_permitida, erro_fora_do_escopo, login_required, require_role

custodia_bp = Blueprint("custodia", __name__)


@custodia_bp.get("/api/custodia/verificar")
@login_required
def verificar_custodia():
    """Sem parâmetro: a cadeia inteira (técnico ou acima). `?incidente_id=N`: só as evidências dele."""
    incidente_id = request.args.get("incidente_id", type=int)
    if incidente_id is None:
        return _verificar_tudo()
    inc = db.session.get(Incidente, incidente_id)
    if inc is None:
        return jsonify({"error": "incidente não encontrado"}), 404
    if not camera_permitida(inc.camera_id):
        return erro_fora_do_escopo()
    resultado = verificar(alert_ids={int(a) for a in (inc.alert_ids or [])})
    return jsonify(resultado | {"incidente_id": incidente_id})


@require_role(ROLE_TECHNICAL)
def _verificar_tudo():
    return jsonify(verificar())


@custodia_bp.get("/api/custodia")
@require_role(ROLE_TECHNICAL)
def listar_elos():
    limite = min(max(request.args.get("limit", 200, type=int) or 200, 1), 1000)
    elos = ElodeCustodia.query.order_by(ElodeCustodia.id.desc()).limit(limite).all()
    total = ElodeCustodia.query.count()
    return jsonify({"items": [e.to_dict() for e in elos], "total": total})
