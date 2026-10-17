"""Retrospectiva da Segurança, estilo "Wrapped" (X7, MISSÃO 2).

Stories de fim de turno e de semana montados SÓ com dados do sistema: o
livro-razão da Liga (app/services/liga.py) e os incidentes. Nada individual:
horas de conformidade são da equipe, destaque é setor, reconhecimento é a
mediana por setor. Sem dado, o card diz que não há dado — não inventa número.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from app.extensions import db
from app.models import Camera, Incidente, Missao, PontoDaLiga
from app.services import liga
from app.utils.texto import pluralizar


def _janela(periodo: str, agora: datetime, turnos: str) -> tuple[datetime, datetime, str]:
    if periodo == "semana":
        inicio, fim = liga.temporada(agora)
        return inicio, min(fim, agora), f"Semana {inicio.astimezone().isocalendar()[1]}"
    t = liga.turno(agora, turnos)
    return t["inicio"], min(t["fim"], agora), f"Turno {t['nome']}"


def _turnos_na_janela(inicio: datetime, fim: datetime, turnos: str) -> list[tuple[datetime, datetime]]:
    janelas, cursor, vistos = [], inicio, set()
    while cursor < fim:
        t = liga.turno(cursor, turnos)
        if t["inicio"] not in vistos:
            vistos.add(t["inicio"])
            janelas.append((max(t["inicio"], inicio), min(t["fim"], fim)))
        cursor = t["fim"] if t["fim"] > cursor else cursor + timedelta(hours=1)
    return janelas


def montar(periodo: str = "turno", agora: datetime | None = None,
           turnos: str = "06:00-14:00,14:00-22:00,22:00-06:00") -> dict[str, Any]:
    agora = agora or datetime.now(timezone.utc)
    inicio, fim, titulo = _janela(periodo, agora, turnos)
    pontos = liga._pontos_entre(inicio, fim)
    por_tipo: dict[str, int] = defaultdict(int)
    for p in pontos:
        por_tipo[p.tipo] += 1
    placar = liga.placar(inicio, fim)

    cards: list[dict[str, Any]] = []
    minutos = por_tipo["minuto_conforme"]
    cards.append({
        "chave": "conformidade", "titulo": "Horas de conformidade da equipe",
        "valor": round(minutos / 60, 1), "unidade": "h",
        "detalhe": f"{pluralizar(minutos, 'minuto')} com gente na câmera e todo mundo com os EPIs exigidos" if minutos
        else "Ainda sem minuto conforme registrado neste período",
    })
    destaque = next((s for s in placar if s["pontos"] > 0), None)
    cards.append({
        "chave": "destaque", "titulo": "Setor destaque",
        "valor": destaque["setor"] if destaque else "Sem dado", "unidade": "",
        "detalhe": f"{destaque['pontos']} pontos de indicadores positivos" if destaque else "Nenhum setor pontuou ainda",
    })

    incidentes = Incidente.query.filter(Incidente.reconhecido_em.isnot(None),
                                        Incidente.reconhecido_em >= inicio.replace(tzinfo=None),
                                        Incidente.reconhecido_em < fim.replace(tzinfo=None)).all()
    cameras = {c.id: c for c in Camera.query.all()}
    tempos_por_setor: dict[str, list[float]] = defaultdict(list)
    for inc in incidentes:
        segundos = inc.to_dict()["reconhecido_em_s"]
        if segundos is not None:
            tempos_por_setor[liga.setor_da_camera(cameras.get(inc.camera_id))].append(segundos)
    todos = [s for lista in tempos_por_setor.values() for s in lista]
    if todos:
        mais_rapido = min(tempos_por_setor.items(), key=lambda kv: median(kv[1]))
        cards.append({
            "chave": "reconhecimento", "titulo": "Incidentes reconhecidos mais rápido",
            "valor": round(median(mais_rapido[1])), "unidade": "s",
            "detalhe": f"Mediana de {mais_rapido[0]} · "
                       f"{pluralizar(len(todos), 'incidente reconhecido', 'incidentes reconhecidos')} na planta, "
                       f"mediana {round(median(todos))} s",
        })
    else:
        cards.append({"chave": "reconhecimento", "titulo": "Incidentes reconhecidos mais rápido", "valor": "Sem dado", "unidade": "",
                      "detalhe": "Nenhum incidente reconhecido neste período"})

    cards.append({
        "chave": "rotulos", "titulo": "Contribuições de rótulo", "valor": por_tipo["rotulo"], "unidade": "",
        "detalhe": "recortes duvidosos revisados pela equipe, que viram dado de treino" if por_tipo["rotulo"]
        else "Nenhum recorte revisado ainda",
    })
    cards.append({
        "chave": "checkins", "titulo": "Check-ins no portal", "valor": por_tipo["checkin_portal"], "unidade": "",
        "detalhe": "entradas liberadas com todos os EPIs exigidos confirmados",
    })

    missoes = Missao.query.filter_by(ativa=True).all()
    cumpridas = 0
    for t_inicio, t_fim in _turnos_na_janela(inicio, fim, turnos):
        no_turno = [p for p in pontos if t_inicio <= liga._utc(p.criado_em) < t_fim]
        cumpridas += sum(1 for m in missoes if liga.progresso_da_missao(m, t_inicio, t_fim, no_turno)["cumprida"])
    cards.append({
        "chave": "missoes", "titulo": "Missões cumpridas", "valor": cumpridas, "unidade": "",
        "detalhe": f"de {pluralizar(len(missoes), 'missão ativa', 'missões ativas')} por turno" if missoes
        else "Nenhuma missão configurada pelo supervisor",
    })
    xp = db.session.query(db.func.coalesce(db.func.sum(PontoDaLiga.pontos), 0)).scalar() or 0
    n = liga.nivel(int(xp))
    cards.append({
        "chave": "nivel", "titulo": "Nível da planta", "valor": n["nivel"], "unidade": "",
        "detalhe": f"{n['xp']} pontos de experiência acumulados · faltam {n['xp_do_proximo'] - n['xp']} para o nível {n['nivel'] + 1}",
    })
    return {"periodo": periodo, "titulo": titulo, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
            "cards": cards, "placar": placar[:5]}
