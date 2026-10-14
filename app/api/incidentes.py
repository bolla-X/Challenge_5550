"""Incidentes (MISSÃO 2, P0.2): o que o painel mostra, agrupando os alertas por pessoa."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.extensions import db, socketio
from app.models import ROLE_OPERATOR, Alert, Incidente
from app.repositories.event_repository import EventRepository
from app.utils.auth import (
    _operador_sem_setor,
    camera_permitida,
    camera_scope,
    current_user,
    erro_fora_do_escopo,
    login_required,
    require_role,
)
from app.utils.salas import emitir_para_camera

incidentes_bp = Blueprint("incidentes", __name__)


def _camera_filtrada() -> int | None:
    escopo = camera_scope()
    return escopo if escopo is not None else request.args.get("camera_id", type=int)


@incidentes_bp.get("/api/incidentes")
@login_required
def listar_incidentes():
    if _operador_sem_setor():
        return jsonify({"items": [], "count": 0})
    consulta = Incidente.query
    camera_id = _camera_filtrada()
    if camera_id is not None:
        consulta = consulta.filter(Incidente.camera_id == camera_id)
    status = request.args.get("status")
    if status in {"active", "resolved"}:
        consulta = consulta.filter(Incidente.status == status)
    limite = min(max(request.args.get("limit", 100, type=int) or 100, 1), 500)
    itens = consulta.order_by(Incidente.aberto_em.desc()).limit(limite).all()
    return jsonify({"items": [i.to_dict() for i in itens], "count": len(itens)})


@incidentes_bp.get("/api/incidentes/<int:incidente_id>")
@login_required
def detalhe_do_incidente(incidente_id: int):
    inc = db.session.get(Incidente, incidente_id)
    if inc is None:
        return jsonify({"error": "incidente não encontrado"}), 404
    if not camera_permitida(inc.camera_id):
        return erro_fora_do_escopo()
    alertas = Alert.query.filter(Alert.id.in_(list(inc.alert_ids or []))).order_by(Alert.created_at).all()
    return jsonify({"incidente": inc.to_dict(), "alertas": [a.to_dict() for a in alertas]})


@incidentes_bp.post("/api/incidentes/<int:incidente_id>/reconhecer")
@require_role(ROLE_OPERATOR)
def reconhecer_incidente(incidente_id: int):
    """"Vi e estou tratando": marca o incidente e os alertas dele. Não resolve nada."""
    inc = db.session.get(Incidente, incidente_id)
    if inc is None:
        return jsonify({"error": "incidente não encontrado"}), 404
    if not camera_permitida(inc.camera_id):
        return erro_fora_do_escopo()
    usuario = current_user()
    agora = datetime.now(timezone.utc)
    primeira_vez = inc.reconhecido_em is None
    if primeira_vez:
        inc.reconhecido_em = agora
        inc.reconhecido_papel = usuario.role if usuario else None
        for alerta in Alert.query.filter(Alert.id.in_(list(inc.alert_ids or []))).all():
            alerta.metadata_json = {**(alerta.metadata_json or {}), "acknowledged": True, "acknowledged_at": agora.isoformat()}
        db.session.commit()
        payload = inc.to_dict()
        # Linha do tempo: o tempo até reconhecer alimenta a Liga de Setores (X8) e a linha causal (X4).
        EventRepository().create(
            event_type="incident_acknowledged",
            severity="info",
            message=f"Incidente reconhecido: {inc.titulo} · {inc.zona}",
            camera_id=inc.camera_id,
            subject=f"incidente:{inc.id}",
            metadata={"incidente_id": inc.id, "segundos": payload["reconhecido_em_s"], "papel": inc.reconhecido_papel},
        )
        emitir_para_camera(socketio, "incident_updated", payload, inc.camera_id)
    return jsonify({"incidente": inc.to_dict(), "primeira_vez": primeira_vez})
