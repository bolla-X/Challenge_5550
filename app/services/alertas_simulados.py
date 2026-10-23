"""Alertas SIMULADOS (histórico de demonstração da Gestão de EPIs): um único jeito de reconhecê-los e de filtrá-los.

O seed (app/services/gestao_seed.py) grava alertas já resolvidos com `metadata_json = {"simulado": true, "seed_id": ...}`.
Quem calcula indicador do painel ao vivo (risco) usa `sem_simulados`, para o seed não mexer no que a planta mostra; quem
só soma e informa (relatório mensal, resumo da Gestão) usa `e_simulado` / `so_simulados` e AVISA quando há simulado.
"""

from __future__ import annotations

from app.extensions import db
from app.models import Alert


def e_simulado(alerta: Alert) -> bool:
    return bool((alerta.metadata_json or {}).get("simulado"))


def _marca():
    return Alert.metadata_json["simulado"].as_boolean()


def sem_simulados(consulta):
    """Só os alertas reais (sem a marca, ou com ela falsa)."""
    return consulta.filter(db.or_(_marca().is_(None), _marca().is_(False)))


def so_simulados(consulta):
    return consulta.filter(_marca().is_(True))
