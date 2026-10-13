"""Laboratório (desligado por padrão): “Pergunte à planta” — ver app/services/pergunte_a_planta.py."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.api.relatorio import montar_relatorio
from app.models import ROLE_TECHNICAL
from app.services.pergunte_a_planta import CATALOGO, PerguntaRecusada, responder
from app.utils.auth import camera_scope, require_role

lab_bp = Blueprint("lab", __name__)


def _disponivel() -> str | None:
    if not current_app.config.get("LAB_PERGUNTE_ATIVO"):
        return "laboratório desligado (LAB_PERGUNTE_ATIVO=false)"
    if not current_app.config.get("LLM_ENABLED") or not current_app.config.get("GEMINI_API_KEY"):
        return "camada LLM desligada (LLM_ENABLED=false ou sem chave)"
    return None


@lab_bp.get("/api/lab/pergunte")
@require_role(ROLE_TECHNICAL)
def estado():
    motivo = _disponivel()
    return jsonify({"disponivel": motivo is None, "motivo": motivo,
                    "catalogo": {nome: c["descricao"] for nome, c in CATALOGO.items()}})


@lab_bp.post("/api/lab/pergunte")
@require_role(ROLE_TECHNICAL)
def perguntar():
    motivo = _disponivel()
    if motivo:
        return jsonify({"error": motivo}), 409
    from app.llm import ProvedorGemini, redigir_segredos

    provedor = ProvedorGemini(api_key=current_app.config.get("GEMINI_API_KEY"), modelo=current_app.config.get("GEMINI_MODEL"),
                              timeout_s=float(current_app.config.get("LLM_TIMEOUT_S", 30)))
    escopo = camera_scope()

    def montar(horas, camera_id):
        return montar_relatorio(horas, escopo if escopo is not None else camera_id)

    try:
        return jsonify(responder(str((request.get_json(silent=True) or {}).get("pergunta", "")), provedor, montar))
    except PerguntaRecusada as exc:
        return jsonify({"error": str(exc), "catalogo": {n: c["descricao"] for n, c in CATALOGO.items()}}), 422
    except Exception as exc:  # noqa: BLE001  (provedor fora do ar não derruba nada)
        return jsonify({"error": redigir_segredos(f"{type(exc).__name__}: {exc}")}), 502
