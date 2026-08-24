from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import Alert

# Estatística simples sobre janela deslizante — não é ML, não prevê nada.

# Teto de normalização: quantos "pontos" (severidade acumulada) numa feature

# já contam como 100%. Ajustável sem tocar no cálculo, conforme dado real.

RISK_SCORE_WINDOW_MINUTES = int(os.getenv("RISK_SCORE_WINDOW_MINUTES", "60"))

RISK_SCORE_MAX_POINTS = float(os.getenv("RISK_SCORE_MAX_POINTS", "20"))



SEVERITY_WEIGHTS: dict[str, float] = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}



FEATURES: tuple[str, ...] = (

    "helmet",

    "vest",

    "gloves",

    "glasses",

    "mask",

    "safety_shoe",

    "falls",

    "posture",

    "risk_area",

)



# (limiar mínimo de score, rótulo) — checado do maior pro menor.

LEVEL_THRESHOLDS: tuple[tuple[float, str], ...] = (

    (75, "critico"),

    (45, "alto"),

    (15, "moderado"),

    (0, "baixo"),

)





def _level_for(score: float) -> str:

    for threshold, label in LEVEL_THRESHOLDS:

        if score >= threshold:

            return label

    return "baixo"





def _score_from_points(points: float) -> float:

    if RISK_SCORE_MAX_POINTS <= 0:

        return 0.0

    return min(100.0, round(points / RISK_SCORE_MAX_POINTS * 100, 1))





def _window_query(window_start: datetime, camera_id: int | None):

    query = Alert.query.filter(Alert.last_seen_at >= window_start)

    if camera_id is not None:

        query = query.filter(Alert.camera_id == camera_id)

    return query





def compute_risk_score(*, now: datetime | None = None, camera_id: int | None = None) -> dict[str, Any]:

    """Frequência recente de alertas por feature, numa janela deslizante.



    Não é predição por IA: é contagem de `Alert` (já debounced pelo

    AlertStateService) ponderada por severidade, dentro da janela. Usa

    `last_seen_at` (não `created_at`) pra incluir violações que começaram

    antes da janela mas continuam ativas/confirmadas dentro dela.

    """

    now = now or datetime.now(timezone.utc)

    window_start = now - timedelta(minutes=RISK_SCORE_WINDOW_MINUTES)



    alerts = _window_query(window_start, camera_id).all()



    points_by_feature: dict[str, float] = {key: 0.0 for key in FEATURES}

    count_by_feature: dict[str, int] = {key: 0 for key in FEATURES}

    for alert in alerts:

        feature = alert.feature

        if feature not in points_by_feature:

            continue

        points_by_feature[feature] += SEVERITY_WEIGHTS.get(alert.severity, 1)

        count_by_feature[feature] += 1



    features_payload: dict[str, dict[str, Any]] = {}

    for key in FEATURES:

        score = _score_from_points(points_by_feature[key])

        features_payload[key] = {

            "score": score,

            "level": _level_for(score),

            "alert_count": count_by_feature[key],

        }



    # Headline = pior categoria atual, não soma das 6 (evita saturar em 100

    # só por ter várias categorias com um pouco de atividade cada).

    worst_key = max(

        FEATURES,

        key=lambda key: (features_payload[key]["score"], features_payload[key]["alert_count"]),

    )

    overall = {

        "score": features_payload[worst_key]["score"],

        "level": features_payload[worst_key]["level"],

        "driving_feature": worst_key if features_payload[worst_key]["alert_count"] else None,

        "alert_count": len(alerts),

    }



    return {

        "camera_id": camera_id,

        "window_minutes": RISK_SCORE_WINDOW_MINUTES,

        "overall": overall,

        "features": features_payload,

        "computed_at": now.isoformat(),

    }





def _bucket_scores(alerts: list[Alert]) -> dict[str, Any]:

    """Mesmo cálculo de compute_risk_score, isolado pra reusar por bucket."""

    points_by_feature: dict[str, float] = {key: 0.0 for key in FEATURES}

    count_by_feature: dict[str, int] = {key: 0 for key in FEATURES}

    for alert in alerts:

        feature = alert.feature

        if feature not in points_by_feature:

            continue

        points_by_feature[feature] += SEVERITY_WEIGHTS.get(alert.severity, 1)

        count_by_feature[feature] += 1



    features_payload: dict[str, dict[str, Any]] = {}

    for key in FEATURES:

        score = _score_from_points(points_by_feature[key])

        features_payload[key] = {"score": score, "level": _level_for(score), "alert_count": count_by_feature[key]}



    worst_key = max(

        FEATURES,

        key=lambda key: (features_payload[key]["score"], features_payload[key]["alert_count"]),

    )

    overall = {"score": features_payload[worst_key]["score"], "level": features_payload[worst_key]["level"]}

    return {"overall": overall, "features": features_payload}





def compute_risk_trend(

    *,

    hours: int = 24,

    bucket_hours: int = 1,

    now: datetime | None = None,

    camera_id: int | None = None,

) -> dict[str, Any]:

    """Série temporal por bucket (padrão: 24 baldes de 1h) sobre o mesmo `Alert`

    já persistido — sem tabela nova. Cada bucket é pontuado isoladamente (não

    é janela deslizante como compute_risk_score): mostra a frequência daquela

    hora específica, o que é o que um sparkline de tendência precisa mostrar.

    """

    now = now or datetime.now(timezone.utc)

    hours = max(1, hours)

    bucket_hours = max(1, bucket_hours)

    num_buckets = max(1, hours // bucket_hours)

    bucket_seconds = bucket_hours * 3600

    window_start = now - timedelta(seconds=bucket_seconds * num_buckets)



    buckets: list[dict[str, Any]] = []

    for i in range(num_buckets):

        end = now - timedelta(seconds=bucket_seconds * (num_buckets - 1 - i))

        start = end - timedelta(seconds=bucket_seconds)

        buckets.append({"start": start, "end": end, "alerts": []})



    alerts = _window_query(window_start, camera_id).all()

    for alert in alerts:

        if alert.last_seen_at is None:

            continue

        # SQLite retorna datetime naive mesmo quando gravamos aware (mesmo

        # comportamento que compute_risk_score já tolera via filtro SQL) —

        # aqui a subtração é em Python, então precisa normalizar antes.

        last_seen_at = alert.last_seen_at if alert.last_seen_at.tzinfo else alert.last_seen_at.replace(tzinfo=timezone.utc)

        age = max(0.0, (now - last_seen_at).total_seconds())

        idx_from_now = int(age // bucket_seconds)

        if idx_from_now >= num_buckets:

            continue

        buckets[num_buckets - 1 - idx_from_now]["alerts"].append(alert)



    return {

        "camera_id": camera_id,

        "hours": hours,

        "bucket_hours": bucket_hours,

        "buckets": [

            {

                "bucket_start": bucket["start"].isoformat(),

                "bucket_end": bucket["end"].isoformat(),

                **_bucket_scores(bucket["alerts"]),

            }

            for bucket in buckets

        ],

    }

