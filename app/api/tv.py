"""Modo TV / Andon (G8): `GET /api/tv` (estado por setor) e metas do setor.

Setor = `Camera.location` (ou o nome da câmera, quando não há local). Tudo é
agregado por setor; nenhum número por pessoa ou por ID de rastreio (princípios
de gamificação da missão, ver app/services/andon.py).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import ROLE_SUPERVISOR, Alert, Camera, MetaDoSetor, utc_now
from app.services.andon import agregar_setor, conquistas
from app.utils.auth import camera_scope, login_required, require_role

tv_bp = Blueprint("tv", __name__)

JANELA_DO_TURNO_H = 8


def _naive(dt):
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


def _setor(camera: Camera) -> str:
    return (camera.location or "").strip() or camera.name


@tv_bp.get("/api/tv")
@login_required
def estado_tv():
    escopo = camera_scope()
    cameras = {c.id: c for c in Camera.query.all() if escopo is None or c.id == escopo}
    resumos = {r["camera_id"]: r for r in current_app.extensions["monitor_service"].andon() if r["camera_id"] in cameras}
    inicio = _naive(utc_now() - timedelta(hours=JANELA_DO_TURNO_H))
    criticos: dict[int, list[Alert]] = defaultdict(list)
    for a in Alert.query.filter(Alert.created_at >= inicio, Alert.severity == "critical").all():
        if a.camera_id in cameras and not (a.metadata_json or {}).get("false_positive"):
            criticos[a.camera_id].append(a)
    metas = {m.setor: m.to_dict() for m in MetaDoSetor.query.all()}

    por_setor: dict[str, list[dict]] = defaultdict(list)
    for cid, camera in cameras.items():
        base = resumos.get(cid) or {"camera_id": cid, "running": False, "conformidade_atual": None, "sequencia_min": 0,
                                    "melhor_sequencia_min": 0, "minutos_com_pessoas": 0, "minutos_conformes": 0,
                                    "epis_sempre_ok": [], "checkins_portal": 0}
        por_setor[_setor(camera)].append({**base, "nome": camera.name})
    setores = []
    for nome, cams in sorted(por_setor.items()):
        setor = agregar_setor(nome, cams)
        ids = [c["camera_id"] for c in cams]
        setor["alertas_criticos"] = sum(len(criticos[i]) for i in ids)
        setor["alertas_reconhecidos"] = sum(1 for i in ids for a in criticos[i] if (a.metadata_json or {}).get("acknowledged"))
        meta = metas.get(nome, {"setor": nome, "minutos_conformes": None, "checkins_portal": None})
        setor["metas"] = meta
        setor["conquistas"] = conquistas(setor, meta)
        setores.append(setor)
    return jsonify({"setores": setores, "janela_h": JANELA_DO_TURNO_H})


@tv_bp.get("/api/tv/metas")
@login_required
def listar_metas():
    return jsonify({"metas": [m.to_dict() for m in MetaDoSetor.query.all()]})


@tv_bp.put("/api/tv/metas/<path:setor>")
@require_role(ROLE_SUPERVISOR)
def definir_meta(setor: str):
    """Body: {"minutos_conformes": 120, "checkins_portal": 30}; null apaga a meta."""
    corpo = request.get_json(silent=True) or {}
    valores = {}
    for chave in ("minutos_conformes", "checkins_portal"):
        if chave in corpo:
            v = corpo[chave]
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > 10_000):
                return jsonify({"error": f"'{chave}' deve ser inteiro entre 1 e 10000, ou null."}), 400
            valores[chave] = v
    if not valores:
        return jsonify({"error": "Envie minutos_conformes e/ou checkins_portal."}), 400
    meta = db.session.get(MetaDoSetor, setor) or MetaDoSetor(setor=setor)
    for chave, v in valores.items():
        setattr(meta, chave, v)
    db.session.add(meta)
    db.session.commit()
    return jsonify(meta.to_dict())
