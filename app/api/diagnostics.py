from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from app.config import BASE_DIR
from app.models import ROLE_TECHNICAL, Alert
from app.repositories.event_repository import EventRepository
from app.services.status_do_sistema import ServicoDeStatus
from app.utils.auth import (
    _operador_sem_setor,
    camera_permitida,
    camera_scope,
    erro_fora_do_escopo,
    escopo_ou_erro,
    login_required,
    require_role,
)

runtime_bp = Blueprint("runtime", __name__)


@runtime_bp.get("/model")
@login_required
def model_diagnostics():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.status(camera_id=camera_id).get("model", {}))


@runtime_bp.get("/api/diagnostics/pipeline")
@login_required
def pipeline_diagnostics():
    """Percentis por etapa do loop de cada câmera (ver app/services/pipeline_stats.py).

    O operador só vê a câmera do setor dele, como em toda rota de câmera.
    """
    if _operador_sem_setor():
        return jsonify({"cameras": {}, "modelos": {}})
    escopo = camera_scope()
    try:
        janela = max(1.0, min(float(request.args.get("janela_s", 30)), 120.0))
    except ValueError:
        janela = 30.0
    # `quadro=K`: instante de captura do K-ésimo quadro lido desde o start
    # (âncora da latência de alerta do scripts/bench.py).
    quadro = request.args.get("quadro", type=int)
    monitor = current_app.extensions["monitor_service"]
    if not hasattr(monitor, "diagnostico_do_pipeline"):
        return jsonify({"cameras": {}, "modelos": {}})
    return jsonify(monitor.diagnostico_do_pipeline([escopo] if escopo is not None else None, janela_s=janela, quadro=quadro))


@runtime_bp.get("/api/status")
@require_role(ROLE_TECHNICAL)
def system_status():
    """Saúde do sistema para a página `/status` (técnico ou acima; operador recebe 403).

    Distinta de `GET /status`, a rota legada do monitor por câmera (app/api/status.py).
    Cada componente é sondado com prazo curto: um que trava ou falha vira um item
    "falha" na resposta, nunca um erro da rota. Ver app/services/status_do_sistema.py.
    """
    servico = current_app.extensions.get("status_do_sistema")
    if servico is None:
        servico = current_app.extensions.setdefault("status_do_sistema", ServicoDeStatus(current_app._get_current_object()))
    resposta = jsonify(servico.montar())
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@runtime_bp.get("/settings")
@login_required
def get_settings():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify(
        {"settings": monitor.settings(camera_id=camera_id), "overlay": monitor.get_overlay(camera_id=camera_id)}
    )


@runtime_bp.patch("/settings")
@require_role(ROLE_TECHNICAL)
def patch_settings():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Dados inválidos."}), 400
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"settings": monitor.update_settings(payload)})


@runtime_bp.get("/overlay")
@login_required
def get_overlay():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"overlay": monitor.get_overlay(camera_id=camera_id)})


@runtime_bp.patch("/overlay")
@require_role(ROLE_TECHNICAL)
def patch_overlay():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Dados inválidos."}), 400
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"overlay": monitor.update_overlay(payload)})


@runtime_bp.get("/risk-area")
@login_required
def get_risk_area():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    if not hasattr(monitor, "risk_area_state"):
        return jsonify({"error": "Este monitor não permite editar a área de risco."}), 501
    return jsonify({"risk_area": monitor.risk_area_state(camera_id=camera_id)})


@runtime_bp.patch("/risk-area")
@require_role(ROLE_TECHNICAL)
def patch_risk_area():
    camera_id, erro = escopo_ou_erro()
    if erro:
        return erro
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Dados inválidos."}), 400
    monitor = current_app.extensions["monitor_service"]
    if not hasattr(monitor, "update_risk_area"):
        return jsonify({"error": "Este monitor não permite editar a área de risco."}), 501
    try:
        return jsonify({"risk_area": monitor.update_risk_area(payload, camera_id=camera_id)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@runtime_bp.get("/events")
@login_required
def list_events():
    try:
        limit = min(int(request.args.get("limit", 80)), 300)
    except ValueError:
        limit = 80
    event_type = request.args.get("event_type")
    severity = request.args.get("severity")
    if _operador_sem_setor():
        return jsonify({"items": [], "count": 0})

    escopo = camera_scope()
    events = EventRepository().list_recent(
        limit=limit,
        event_type=event_type,
        severity=severity,
        camera_id=escopo if escopo is not None else request.args.get("camera_id", type=int),
    )
    return jsonify({"items": [item.to_dict() for item in events], "count": len(events)})


@runtime_bp.get("/snapshots/<path:filename>")
@login_required
def get_snapshot(filename: str):
    # Mesmo escopo de `/alerts/<id>/evidence`, que serve o mesmo arquivo: a
    # imagem pertence a um alerta, e o alerta a uma câmera. Arquivo sem alerta
    # não é servido (matriz de permissões, MISSÃO 4).
    alerta = Alert.query.filter(Alert.frame_ref == f"/snapshots/{filename}").first()
    if alerta is None:
        return jsonify({"error": "imagem não encontrada"}), 404
    if not camera_permitida(alerta.camera_id):
        return erro_fora_do_escopo()
    monitor = current_app.extensions.get("monitor_service")
    snapshot_dir = "runtime/snapshots"
    if monitor is not None and hasattr(monitor, "snapshot_service"):
        snapshot_dir = monitor.snapshot_service.snapshot_dir
    directory = Path(snapshot_dir)
    if not directory.is_absolute():
        directory = Path(BASE_DIR) / directory
    return send_from_directory(directory, filename, as_attachment=False)
