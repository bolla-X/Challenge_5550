"""Simulador "E se?" de regras (X2): técnico ou acima. Nunca altera alerta real."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import ROLE_TECHNICAL, Alert, Camera
from app.services.risk_rules import PPE_RULES
from app.services.simulador import Parametros, baldes, regra_simulavel, simular
from app.utils.auth import require_role
from app.vision.person_compliance_matcher import PPE_LABELS

simulador_bp = Blueprint("simulador", __name__)


def _worker(camera_id: int):
    try:
        return current_app.extensions["monitor_service"].worker_da_camera(camera_id)
    except LookupError:
        return None


def _parametros_atuais(worker) -> dict:
    cfg = current_app.config
    return {
        "epis": sorted(k for k in PPE_RULES if worker is not None and worker.feature_manager.is_enabled(k)),
        "zona": [[round(x, 4), round(y, 4)] for x, y in (worker.rule_engine.risk_polygon if worker is not None else [])],
        "zona_nome": worker.risk_area_name if worker is not None else None,
        "zona_ligada": bool(worker is not None and worker.feature_manager.is_enabled("risk_area")),
        "criar_apos_quadros": int(cfg.get("ALERT_CREATE_AFTER_FRAMES", 8)),
        "criar_apos_s": float(cfg.get("ALERT_CREATE_AFTER_SECONDS", 0)) or None,
        "min_confirmacoes": int(cfg.get("ALERT_MIN_CONFIRMATIONS", 2)),
        "resolver_apos_quadros": int(cfg.get("ALERT_RESOLVE_AFTER_FRAMES", 20)),
        "resolver_apos_s": float(cfg.get("ALERT_RESOLVE_AFTER_SECONDS", 0)) or None,
        "min_confirmacoes_resolver": int(cfg.get("ALERT_MIN_RESOLVE_CONFIRMATIONS", 3)),
    }


def _parametros(base: dict, corpo: dict) -> Parametros:
    epis = corpo.get("epis", base["epis"])
    zona = corpo.get("zona", base["zona"] if base["zona_ligada"] else None)
    histerese = corpo.get("criar_apos_s", base["criar_apos_s"])
    return Parametros(
        epis=frozenset(str(e) for e in epis if str(e) in PPE_RULES),
        zona=tuple((float(x), float(y)) for x, y in zona) if zona and len(zona) >= 3 else None,
        criar_apos_quadros=max(1, int(corpo.get("criar_apos_quadros", base["criar_apos_quadros"]))),
        criar_apos_s=float(histerese) if histerese not in (None, "", 0) else None,
        min_confirmacoes=base["min_confirmacoes"],
        resolver_apos_quadros=base["resolver_apos_quadros"],
        resolver_apos_s=base["resolver_apos_s"],
        min_confirmacoes_resolver=base["min_confirmacoes_resolver"],
    )


@simulador_bp.get("/api/simulador/contexto")
@require_role(ROLE_TECHNICAL)
def contexto():
    """O que a tela precisa para começar: regra atual e quanto de trilha existe."""
    camera_id = request.args.get("camera_id", type=int)
    camera = db.session.get(Camera, camera_id) if camera_id is not None else None
    if camera is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    worker = _worker(camera_id)
    trilhas = worker.trilhas if worker is not None else None
    primeiro = ultimo = None
    registros = 0
    epis_gravados: set[str] = set()
    if trilhas is not None:
        for r in trilhas.ler():
            registros += 1
            primeiro = primeiro if primeiro is not None else r["t"]
            ultimo = r["t"]
            for pessoa in r.get("p") or []:
                epis_gravados.update((pessoa[5] or {}).keys())
    return jsonify({
        "camera_id": camera_id,
        "atual": _parametros_atuais(worker),
        "trilha": {"registros": registros, "primeiro": primeiro, "ultimo": ultimo,
                   "bytes": trilhas.tamanho_total() if trilhas is not None else 0},
        "epis_com_dado": sorted(epis_gravados),
        "rotulos": {k: PPE_LABELS.get(k, k) for k in PPE_RULES},
    })


@simulador_bp.post("/api/simulador")
@require_role(ROLE_TECHNICAL)
def rodar():
    """Body: {camera_id, horas, epis?: [...], zona?: [[x,y],...] | null, criar_apos_s?: float}."""
    corpo = request.get_json(silent=True) or {}
    try:
        camera_id = int(corpo.get("camera_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "camera_id obrigatório"}), 400
    if db.session.get(Camera, camera_id) is None:
        return jsonify({"error": "câmera não encontrada"}), 404
    worker = _worker(camera_id)
    if worker is None or worker.trilhas is None:
        return jsonify({"error": "câmera sem trilha gravada (ligue a câmera e espere algumas análises)"}), 409
    try:
        horas = float(corpo.get("horas", 1))
        if not math.isfinite(horas):
            raise ValueError("horas não finito")
    except (TypeError, ValueError):
        return jsonify({"error": "horas deve ser um número finito (ex.: 1 ou 0.5)"}), 400
    horas = min(max(horas, 0.01), 72.0)
    fim = time.time()
    inicio = fim - horas * 3600
    registros = list(worker.trilhas.ler(desde=inicio, ate=fim))
    if registros:
        inicio = max(inicio, registros[0]["t"])
    base = _parametros_atuais(worker)
    try:
        proposta = _parametros(base, corpo)
    except (TypeError, ValueError):
        return jsonify({"error": "parâmetros inválidos"}), 400
    atual = _parametros(base, {})
    balde_s = max(10.0, (fim - inicio) / 60)
    t0 = time.perf_counter()
    simulado = simular(registros, proposta).resumo(inicio, fim, balde_s)
    com_regra_atual = simular(registros, atual).resumo(inicio, fim, balde_s)
    custo_ms = (time.perf_counter() - t0) * 1000
    reais = (
        Alert.query.filter(
            Alert.camera_id == camera_id,
            Alert.created_at >= datetime.fromtimestamp(inicio, tz=timezone.utc),
            Alert.created_at <= datetime.fromtimestamp(fim, tz=timezone.utc),
        ).all()
    )
    instantes = []
    por_regra: dict[str, int] = {}
    for a in reais:
        if not regra_simulavel(a.rule):
            continue
        criado = a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)
        instantes.append(criado.timestamp())
        por_regra[a.rule] = por_regra.get(a.rule, 0) + 1
    return jsonify({
        "camera_id": camera_id,
        "janela": [inicio, fim],
        "balde_s": balde_s,
        "registros": len(registros),
        "proposta": {"epis": sorted(proposta.epis), "zona": [list(p) for p in proposta.zona] if proposta.zona else None,
                     "criar_apos_s": proposta.criar_apos_s},
        "simulado": simulado,
        "com_regra_atual": com_regra_atual,
        "real": {"total": len(instantes), "por_regra": por_regra, "linha": baldes(instantes, inicio, fim, balde_s)},
        "custo_ms": round(custo_ms, 1),
    })
