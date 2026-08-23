from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.risk_score_service import compute_risk_score, compute_risk_trend

risk_bp = Blueprint("risk", __name__)


@risk_bp.get("/risk-score")
def risk_score():
    return jsonify(compute_risk_score())


@risk_bp.get("/risk-score/trend")
def risk_score_trend():
    hours = request.args.get("hours", default=24, type=int)
    bucket_hours = request.args.get("bucket_hours", default=1, type=int)
    # Clamp: sparkline não precisa (nem deveria aceitar) baldes fora de uma
    # janela razoável — protege contra ?hours=999999 gerando resposta gigante.
    hours = max(1, min(hours, 24 * 14))
    bucket_hours = max(1, min(bucket_hours, 24))
    return jsonify(compute_risk_trend(hours=hours, bucket_hours=bucket_hours))
