"""Editor de regras sem código (M4): técnico ou acima.

Salvar, ativar, desativar e excluir recompilam as regras ativas e as entregam
ao RuleEngine de cada câmera (`aplicar_regras`). "Testar no histórico" nunca
cria nem muda alerta real: só lê a trilha gravada (a mesma do simulador X2).
"""

from __future__ import annotations

import time

from flask import Blueprint, current_app, jsonify, request

from app.api.simulador import _parametros, _parametros_atuais, _worker
from app.extensions import db
from app.models import ROLE_TECHNICAL, Camera
from app.services.regras_editor import (
    BLOCOS_MAXIMOS,
    EPI_ESTADOS,
    POSTURAS,
    PROFUNDIDADE_MAXIMA,
    SEVERIDADES,
    Regra,
    RegraInvalida,
    testar_no_historico,
    validar,
)
from app.services.regras_repositorio import (
    RegraJaExiste,
    RegraNaoEncontrada,
    RegraProtegida,
    aplicar_regras,
    atualizar_regra,
    criar_regra,
    definir_ativa,
    excluir_regra,
    listar_regras_gestao,
)
from app.utils.auth import current_user, require_role
from app.vision.person_compliance_matcher import PPE_KEYS, PPE_LABELS

regras_bp = Blueprint("regras", __name__)

HORAS_MINIMAS, HORAS_MAXIMAS = 1, 24


def _serializar(regra: Regra) -> dict:
    return regra.to_dict() | {"protegida": regra.origem == "pre_carregada"}


def _invalida(erro: RegraInvalida):
    return jsonify({"error": str(erro), "code": "regra_invalida"}), 400


def _nao_encontrada():
    return jsonify({"error": "regra não encontrada", "code": "regra_nao_encontrada"}), 404


def _protegida():
    return jsonify({"error": "regra pré-carregada não pode ser editada nem excluída; duplique-a e edite a cópia",
                    "code": "regra_protegida"}), 409


def _corpo() -> dict | None:
    corpo = request.get_json(silent=True)
    return corpo if isinstance(corpo, dict) else None


@regras_bp.get("/api/regras")
@require_role(ROLE_TECHNICAL)
def listar():
    return jsonify({
        "regras": [_serializar(regra) for regra in listar_regras_gestao()],
        "limites": {"profundidade": PROFUNDIDADE_MAXIMA, "blocos": BLOCOS_MAXIMOS},
        "opcoes": {"severidades": list(SEVERIDADES), "epis": {k: PPE_LABELS.get(k, k) for k in PPE_KEYS},
                   "estados_epi": list(EPI_ESTADOS), "posturas": list(POSTURAS)},
    })


@regras_bp.post("/api/regras")
@require_role(ROLE_TECHNICAL)
def criar():
    corpo = _corpo()
    if corpo is None:
        return jsonify({"error": "corpo JSON obrigatório", "code": "regra_invalida"}), 400
    usuario = current_user()
    try:
        regra = criar_regra(corpo, criada_por=getattr(usuario, "email", None))
    except RegraInvalida as erro:
        return _invalida(erro)
    except RegraJaExiste:
        return jsonify({"error": "já existe uma regra com este id", "code": "regra_ja_existe"}), 409
    aplicar_regras(current_app)
    return jsonify({"regra": _serializar(regra)}), 201


@regras_bp.put("/api/regras/<regra_id>")
@require_role(ROLE_TECHNICAL)
def atualizar(regra_id: str):
    corpo = _corpo()
    if corpo is None:
        return jsonify({"error": "corpo JSON obrigatório", "code": "regra_invalida"}), 400
    try:
        regra = atualizar_regra(regra_id, corpo)
    except RegraNaoEncontrada:
        return _nao_encontrada()
    except RegraProtegida:
        return _protegida()
    except RegraInvalida as erro:
        return _invalida(erro)
    aplicar_regras(current_app)
    return jsonify({"regra": _serializar(regra)})


@regras_bp.delete("/api/regras/<regra_id>")
@require_role(ROLE_TECHNICAL)
def excluir(regra_id: str):
    try:
        excluir_regra(regra_id)
    except RegraNaoEncontrada:
        return _nao_encontrada()
    except RegraProtegida:
        return _protegida()
    aplicar_regras(current_app)
    return jsonify({"ok": True})


def _ligar(regra_id: str, ativa: bool):
    try:
        regra = definir_ativa(regra_id, ativa)
    except RegraNaoEncontrada:
        return _nao_encontrada()
    aplicar_regras(current_app)
    return jsonify({"regra": _serializar(regra)})


@regras_bp.post("/api/regras/<regra_id>/ativar")
@require_role(ROLE_TECHNICAL)
def ativar(regra_id: str):
    return _ligar(regra_id, True)


@regras_bp.post("/api/regras/<regra_id>/desativar")
@require_role(ROLE_TECHNICAL)
def desativar(regra_id: str):
    return _ligar(regra_id, False)


@regras_bp.post("/api/regras/testar")
@require_role(ROLE_TECHNICAL)
def testar():
    """Body: {regra: {...}, camera_id, horas: 1..24}. A regra pode ser rascunho (sem id/nome)."""
    corpo = _corpo() or {}
    try:
        camera_id = int(corpo.get("camera_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "camera_id obrigatório", "code": "camera_invalida"}), 400
    try:
        horas = float(corpo.get("horas", 1))
    except (TypeError, ValueError):
        horas = 0.0
    if not HORAS_MINIMAS <= horas <= HORAS_MAXIMAS:
        return jsonify({"error": f"horas precisa estar entre {HORAS_MINIMAS} e {HORAS_MAXIMAS}", "code": "horas_invalidas"}), 400
    rascunho = corpo.get("regra")
    if not isinstance(rascunho, dict):
        return _invalida(RegraInvalida("regra: obrigatória"))
    try:
        regra = validar({"id": "teste", "nome": "Teste", **rascunho, "origem": "usuario"})
    except RegraInvalida as erro:
        return _invalida(erro)
    if db.session.get(Camera, camera_id) is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    worker = _worker(camera_id)
    if worker is None or worker.trilhas is None:
        return jsonify({"error": "câmera sem trilha gravada (ligue a câmera e espere algumas análises)"}), 409
    fim = time.time()
    inicio = fim - horas * 3600
    registros = list(worker.trilhas.ler(desde=inicio, ate=fim))
    if registros:
        inicio = max(inicio, registros[0]["t"])
    base = _parametros_atuais(worker)
    zona = base["zona"] if base["zona_ligada"] and len(base["zona"]) >= 3 else None
    resultado = testar_no_historico(regra, registros, inicio, fim, zona=zona, parametros=_parametros(base, {}))
    return jsonify({"camera_id": camera_id, "janela": [inicio, fim], "registros": len(registros), **resultado})
