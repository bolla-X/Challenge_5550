"""Gêmeo digital (X1, MISSÃO 2): a planta inteira, com todas as câmeras calibradas (G5).

Cada câmera com calibração entra com:
- o quadrilátero do chão que ela vê, na planta (vira o cone de visão no 3D);
- a zona de risco levada para a planta pela homografia;
- os pés de cada pessoa rastreada, com o estado de conformidade (cor do avatar);
- os incidentes ativos.

Nada de imagem: o avatar é uma cápsula colorida, nunca foto. IDs são de
rastreio, por câmera — não identidade.
"""

from __future__ import annotations

import time

from flask import Blueprint, current_app, jsonify

from app.models import Camera
from app.utils.auth import camera_scope, login_required
from app.vision.planta import poligono_na_planta

gemeo_bp = Blueprint("gemeo", __name__)


def _alertas_por_pessoa(worker) -> dict[str, int]:
    """person_id -> id do alerta ativo mais grave (para o replay ao clicar no avatar)."""
    ordem = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    melhor: dict[str, tuple[int, int]] = {}
    for alerta in worker.alert_state_service.active_alerts():
        pid = str((alerta.get("metadata") or {}).get("person_id") or "")
        if not pid:
            continue
        chave = (ordem.get(alerta.get("severity"), 9), -int(alerta.get("id") or 0))
        if pid not in melhor or chave < melhor[pid]:
            melhor[pid] = chave
    return {pid: -chave[1] for pid, chave in melhor.items()}


@gemeo_bp.get("/api/gemeo")
@login_required
def estado_do_gemeo():
    monitor = current_app.extensions["monitor_service"]
    escopo = camera_scope()
    consulta = Camera.query.order_by(Camera.id)
    if escopo is not None:
        consulta = consulta.filter(Camera.id == escopo)
    cameras = []
    for camera in consulta.all():
        item = {
            "id": camera.id,
            "nome": camera.name,
            "setor": camera.location or camera.name,
            "calibrada": bool(camera.planta),
            "pontos_camera": (camera.planta or {}).get("pontos_camera"),
            "pontos_planta": (camera.planta or {}).get("pontos_planta"),
            "zona": [],
            "zona_nome": None,
            "pes": [],
            "incidentes": [],
            "rodando": False,
        }
        try:
            worker = monitor.worker_da_camera(camera.id)
        except LookupError:
            cameras.append(item)
            continue
        item["rodando"] = bool(worker._running.is_set())
        item["incidentes"] = worker.alert_state_service.active_incidents()
        if camera.planta:
            poligono = list(worker.rule_engine.risk_polygon or [])
            try:
                item["zona"] = poligono_na_planta(poligono, camera.planta)
            except (ValueError, KeyError):
                item["zona"] = []
            item["zona_nome"] = worker.risk_area_name if poligono else None
            alertas = _alertas_por_pessoa(worker)
            item["pes"] = [
                pe | {"alert_id": alertas.get(f"person_{pe['track_id']}") or alertas.get(str(pe["track_id"]))}
                for pe in list(worker.pes_na_planta or [])
            ]
        cameras.append(item)
    return jsonify({"cameras": cameras, "gerado_em": time.time()})
