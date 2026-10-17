"""Intervenções, antes/depois e ROI (MISSÃO 4, M8). Regras e limites: app/services/intervencoes.py.

Papéis: Supervisor cria, edita e apaga; Técnico ou mais lê, compara e calcula o ROI
(o ROI só faz aritmética com o que vem no corpo: não grava nada).
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import ROLE_SUPERVISOR, ROLE_TECHNICAL, Intervencao
from app.services import intervencoes as servico
from app.utils.auth import current_user, require_role

intervencoes_bp = Blueprint("intervencoes", __name__)

_STATUS_DO_CODIGO = {"camera_nao_encontrada": 404}


def _erro(exc: servico.DadoInvalido):
    return jsonify({"error": exc.message, "code": exc.code}), _STATUS_DO_CODIGO.get(exc.code, 400)


def _quem() -> str:
    usuario = current_user()
    return usuario.email if usuario is not None else "sistema"


def _nao_encontrada():
    return jsonify({"error": "intervenção não encontrada"}), 404


@intervencoes_bp.get("/api/intervencoes")
@require_role(ROLE_TECHNICAL)
def listar_intervencoes():
    consulta = Intervencao.query
    camera_id = request.args.get("camera_id", type=int)
    if camera_id is not None:
        consulta = consulta.filter(Intervencao.camera_id == camera_id)
    setor = (request.args.get("setor") or "").strip()
    if setor:
        consulta = consulta.filter(Intervencao.setor == setor)
    itens = consulta.order_by(Intervencao.data_da_intervencao.desc(), Intervencao.id.desc()).limit(500).all()
    return jsonify({"items": [i.to_dict() for i in itens], "count": len(itens)})


@intervencoes_bp.post("/api/intervencoes")
@require_role(ROLE_SUPERVISOR)
def criar_intervencao():
    try:
        nova = servico.aplicar(Intervencao(criada_por=_quem()), request.get_json(silent=True))
    except servico.DadoInvalido as exc:
        return _erro(exc)
    db.session.add(nova)
    db.session.commit()
    return jsonify({"intervencao": nova.to_dict()}), 201


@intervencoes_bp.get("/api/intervencoes/<int:intervencao_id>")
@require_role(ROLE_TECHNICAL)
def detalhe_da_intervencao(intervencao_id: int):
    item = db.session.get(Intervencao, intervencao_id)
    if item is None:
        return _nao_encontrada()
    return jsonify({"intervencao": item.to_dict()})


@intervencoes_bp.put("/api/intervencoes/<int:intervencao_id>")
@require_role(ROLE_SUPERVISOR)
def editar_intervencao(intervencao_id: int):
    item = db.session.get(Intervencao, intervencao_id)
    if item is None:
        return _nao_encontrada()
    try:
        servico.aplicar(item, request.get_json(silent=True))
    except servico.DadoInvalido as exc:
        db.session.rollback()
        return _erro(exc)
    db.session.commit()
    return jsonify({"intervencao": item.to_dict()})


@intervencoes_bp.delete("/api/intervencoes/<int:intervencao_id>")
@require_role(ROLE_SUPERVISOR)
def apagar_intervencao(intervencao_id: int):
    item = db.session.get(Intervencao, intervencao_id)
    if item is None:
        return _nao_encontrada()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"deleted": intervencao_id})


@intervencoes_bp.get("/api/intervencoes/<int:intervencao_id>/comparacao")
@require_role(ROLE_TECHNICAL)
def comparar_intervencao(intervencao_id: int):
    item = db.session.get(Intervencao, intervencao_id)
    if item is None:
        return _nao_encontrada()
    try:
        janela = servico.janela_valida(request.args.get("janela_dias"))
    except servico.DadoInvalido as exc:
        return _erro(exc)
    return jsonify(servico.comparar(item, janela, datetime.now(timezone.utc)))


@intervencoes_bp.post("/api/intervencoes/<int:intervencao_id>/roi")
@require_role(ROLE_TECHNICAL)
def roi_da_intervencao(intervencao_id: int):
    item = db.session.get(Intervencao, intervencao_id)
    if item is None:
        return _nao_encontrada()
    try:
        resultado = servico.calcular_roi(request.get_json(silent=True))
    except servico.DadoInvalido as exc:
        return _erro(exc)
    return jsonify({"intervencao_id": item.id, **resultado})
