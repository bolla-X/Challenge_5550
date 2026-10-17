"""Integração industrial (M2): o estado que vai para OPC UA/MQTT e a torre de luz.

`GET /api/integracao/estado` devolve o MESMO `estado_da_planta` publicado nos
nós OPC UA e no tópico `visionepi/planta/estado`, mais o status de cada
integração (no ar, desligada, falhou + motivo). O Operador vê só a própria
câmera: o estado é recalculado só com ela, para a torre dele não acender por
outro setor e para não vazar o estado das outras áreas.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.services.integracao.estado import estado_da_planta
from app.utils.auth import escopo_ou_erro, login_required

integracao_bp = Blueprint("integracao", __name__)


@integracao_bp.get("/api/integracao/estado")
@login_required
def estado():
    escopo, erro = escopo_ou_erro()
    if erro:
        return erro
    monitor = current_app.extensions["monitor_service"]
    planta = monitor.estado_da_planta()
    if escopo is not None:
        planta = estado_da_planta([c for c in planta.get("cameras", []) if c.get("id") == escopo])
    return jsonify({"planta": planta, "integracoes": monitor.integracao.status()})
