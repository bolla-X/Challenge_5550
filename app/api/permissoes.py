"""Permissão de Trabalho digital (MISSÃO 4, M5). Regras e citação da norma: app/services/permissoes.py."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import PERMISSAO_STATUS, ROLE_TECHNICAL, Camera, PermissaoDeTrabalho, utc_now
from app.services import permissoes as servico
from app.utils.auth import (
    _operador_sem_setor,
    camera_permitida,
    camera_scope,
    current_user,
    erro_fora_do_escopo,
    login_required,
    require_role,
)

permissoes_bp = Blueprint("permissoes", __name__)

# Erro de regra → HTTP. `permissao_nao_ativa` é conflito de estado (a PT já foi
# encerrada/cancelada); o resto é payload inválido.
_STATUS_DO_CODIGO = {"permissao_nao_ativa": 409}


def _erro(exc: servico.PermissaoInvalida):
    return jsonify({"error": exc.message, "code": exc.code}), _STATUS_DO_CODIGO.get(exc.code, 400)


def _quem() -> str:
    usuario = current_user()
    return usuario.email if usuario is not None else "sistema"


def _camera_filtrada() -> int | None:
    """Operador só enxerga a câmera do setor dele; os demais podem filtrar por ?camera_id=."""
    escopo = camera_scope()
    return escopo if escopo is not None else request.args.get("camera_id", type=int)


def _epis_suportados(camera_id: int) -> set[str]:
    """EPIs que o modelo da câmera detecta. Sem worker, nada é automático: nunca fingimos checagem."""
    try:
        return set(current_app.extensions["monitor_service"].worker_da_camera(camera_id).rule_engine.supported_ppe())
    except (LookupError, AttributeError, KeyError):
        return set()


def _detalhe(permissao: PermissaoDeTrabalho) -> dict:
    return servico.detalhar_permissao(permissao, _epis_suportados(permissao.camera_id), utc_now())


@permissoes_bp.get("/api/permissoes")
@login_required
def listar_permissoes():
    if _operador_sem_setor():
        return jsonify({"items": [], "count": 0})
    status = request.args.get("status")
    if status is not None and status not in PERMISSAO_STATUS:
        return jsonify({"error": f"'status' deve ser um de {list(PERMISSAO_STATUS)}.", "code": "campo_invalido"}), 400
    limite = min(max(request.args.get("limit", 200, type=int) or 200, 1), 500)
    itens = servico.listar_gerenciamento_permissoes(camera_id=_camera_filtrada(), status=status, limite=limite)
    agora = utc_now()
    return jsonify({"items": [p.to_dict(agora) for p in itens], "count": len(itens)})


@permissoes_bp.post("/api/permissoes")
@require_role(ROLE_TECHNICAL)
def emitir_permissao():
    try:
        permissao, avisos = servico.emitir_permissao(request.get_json(silent=True), criada_por=_quem())
    except servico.PermissaoInvalida as exc:
        return _erro(exc)
    except LookupError:
        return jsonify({"error": "câmera não encontrada"}), 404
    return jsonify(_detalhe(permissao) | {"avisos": avisos}), 201


@permissoes_bp.get("/api/permissoes/<int:permissao_id>")
@login_required
def detalhe_da_permissao(permissao_id: int):
    permissao = db.session.get(PermissaoDeTrabalho, permissao_id)
    if permissao is None:
        return jsonify({"error": "permissão não encontrada"}), 404
    if not camera_permitida(permissao.camera_id):
        return erro_fora_do_escopo()
    return jsonify(_detalhe(permissao))


def _finalizar(acao, permissao_id: int):
    try:
        permissao = acao(permissao_id, por=_quem())
    except servico.PermissaoInvalida as exc:
        return _erro(exc)
    except LookupError:
        return jsonify({"error": "permissão não encontrada"}), 404
    return jsonify(_detalhe(permissao))


@permissoes_bp.post("/api/permissoes/<int:permissao_id>/encerrar")
@require_role(ROLE_TECHNICAL)
def encerrar_permissao(permissao_id: int):
    return _finalizar(servico.encerrar_permissao, permissao_id)


@permissoes_bp.post("/api/permissoes/<int:permissao_id>/cancelar")
@require_role(ROLE_TECHNICAL)
def cancelar_permissao(permissao_id: int):
    return _finalizar(servico.cancelar_permissao, permissao_id)


@permissoes_bp.get("/api/cameras/<int:camera_id>/zona-controlada")
@login_required
def obter_zona_controlada(camera_id: int):
    if not camera_permitida(camera_id):
        return erro_fora_do_escopo()
    if db.session.get(Camera, camera_id) is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    return jsonify(servico.obter_zona_controlada(camera_id))


@permissoes_bp.put("/api/cameras/<int:camera_id>/zona-controlada")
@require_role(ROLE_TECHNICAL)
def definir_zona_controlada(camera_id: int):
    """Body: {"exige_permissao": true|false}. Liga/desliga "a área de risco desta câmera exige permissão"."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict) or not isinstance(corpo.get("exige_permissao"), bool):
        return jsonify({"error": "Envie {\"exige_permissao\": true|false}.", "code": "campo_invalido"}), 400
    try:
        return jsonify(servico.definir_zona_controlada(camera_id, corpo["exige_permissao"], por=_quem()))
    except LookupError:
        return jsonify({"error": "câmera não encontrada"}), 404
