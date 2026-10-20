"""Liga de Setores, missões e nível da planta (X8, MISSÃO 2).

Princípios (os mesmos do G8, agora com pontos):
- só indicador POSITIVO vira ponto: check-in no portal, incidente reconhecido
  rápido, falso positivo revisado, rótulo contribuído, minuto conforme;
- nunca ponto negativo; nunca premiar "zero alertas" (minuto sem ninguém na
  câmera é neutro); gerar ou reportar alerta não custa nada a ninguém;
- tudo por SETOR (`Camera.location`); nada por pessoa ou ID de rastreio.

Temporada = semana ISO (segunda 00:00 até domingo, hora local do servidor).
Turnos vêm de `TURNOS` ("06:00-14:00,14:00-22:00,22:00-06:00").
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Camera, Missao, PontoDaLiga

logger = logging.getLogger(__name__)

PONTOS = {
    "checkin_portal": 10,
    "reconhecido_rapido": 15,  # incidente reconhecido em até 60 s
    "reconhecido": 5,  # em até 3 min
    "falso_positivo_revisado": 5,
    "rotulo": 2,
    "minuto_conforme": 1,
}
ROTULOS = {
    "checkin_portal": "Check-ins no portal",
    "reconhecido_rapido": "Reconhecidos em até 1 min",
    "reconhecido": "Reconhecidos em até 3 min",
    "falso_positivo_revisado": "Falsos positivos revisados",
    "rotulo": "Rótulos contribuídos",
    "minuto_conforme": "Minutos conformes",
}
# Faixas do mesmo fato: reconhecer o incidente (ou o alerta dele) vale UM ponto,
# na faixa em que o primeiro reconhecimento caiu; o segundo não soma outra faixa.
FAIXAS_DO_MESMO_FATO = {
    "reconhecido_rapido": ("reconhecido_rapido", "reconhecido"),
    "reconhecido": ("reconhecido_rapido", "reconhecido"),
}
TIPOS_DE_MISSAO = ("checkin_portal", "rotulo", "reconhecido_rapido", "minuto_conforme")


def setor_da_camera(camera: Camera | None) -> str:
    if camera is None:
        return "Planta"
    return (camera.location or "").strip() or camera.name


def _utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)


def registrar(tipo: str, *, ref: str, camera_id: int | None = None, setor: str | None = None,
              quando: datetime | None = None, commit: bool = True) -> PontoDaLiga | None:
    """Anota um ponto. Repetir o mesmo (tipo, ref) não conta de novo."""
    if tipo not in PONTOS:
        raise ValueError(f"tipo de ponto desconhecido: {tipo}")
    try:
        if setor is None:
            setor = setor_da_camera(db.session.get(Camera, camera_id) if camera_id is not None else None)
        equivalentes = FAIXAS_DO_MESMO_FATO.get(tipo, (tipo,))
        if PontoDaLiga.query.filter(PontoDaLiga.tipo.in_(equivalentes), PontoDaLiga.ref == ref[:120]).first() is not None:
            return None
        ponto = PontoDaLiga(setor=setor, camera_id=camera_id, tipo=tipo, pontos=PONTOS[tipo], ref=ref[:120],
                            criado_em=_utc(quando or datetime.now(timezone.utc)))
        db.session.add(ponto)
        if commit:
            db.session.commit()
        return ponto
    except IntegrityError:
        db.session.rollback()
        return None
    except Exception as exc:  # noqa: BLE001  (a liga nunca derruba quem gerou o fato)
        db.session.rollback()
        logger.warning("liga_ponto_falhou", extra={"tipo": tipo, "error": str(exc)})
        return None


def pontos_do_reconhecimento(segundos: float | None) -> str | None:
    if segundos is None:
        return None
    if segundos <= 60:
        return "reconhecido_rapido"
    if segundos <= 180:
        return "reconhecido"
    return None


# ------------------------------------------------------------- tempo
def temporada(agora: datetime | None = None) -> tuple[datetime, datetime]:
    local = (agora or datetime.now(timezone.utc)).astimezone()
    inicio = datetime.combine((local - timedelta(days=local.weekday())).date(), time.min, tzinfo=local.tzinfo)
    return inicio.astimezone(timezone.utc), (inicio + timedelta(days=7)).astimezone(timezone.utc)


def _hora(texto: str) -> time:
    h, m = texto.strip().split(":")
    return time(int(h), int(m))


def turno(agora: datetime | None = None, turnos: str = "06:00-14:00,14:00-22:00,22:00-06:00") -> dict[str, Any]:
    local = (agora or datetime.now(timezone.utc)).astimezone()
    for faixa in [t for t in turnos.split(",") if "-" in t]:
        a, b = (_hora(x) for x in faixa.split("-"))
        hoje = local.date()
        for dia in (hoje, hoje - timedelta(days=1)):
            inicio = datetime.combine(dia, a, tzinfo=local.tzinfo)
            fim = datetime.combine(dia if b > a else dia + timedelta(days=1), b, tzinfo=local.tzinfo)
            if inicio <= local < fim:
                return {"nome": faixa.strip(), "inicio": inicio.astimezone(timezone.utc), "fim": fim.astimezone(timezone.utc)}
    inicio = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    return {"nome": "dia", "inicio": inicio.astimezone(timezone.utc), "fim": (inicio + timedelta(days=1)).astimezone(timezone.utc)}


# ------------------------------------------------------------- nível
def nivel(xp: int) -> dict[str, Any]:
    """Nível n começa em 50·n·(n−1) XP: 1→0, 2→100, 3→300, 4→600, 5→1000…"""
    n = max(1, int((1 + math.sqrt(1 + 4 * max(0, xp) / 50)) / 2))
    while 50 * (n + 1) * n <= xp:
        n += 1
    base, proximo = 50 * n * (n - 1), 50 * (n + 1) * n
    return {"nivel": n, "xp": xp, "xp_do_nivel": base, "xp_do_proximo": proximo,
            "progresso": round((xp - base) / max(1, proximo - base), 3)}


# ------------------------------------------------------------- consultas
def _pontos_entre(inicio: datetime, fim: datetime) -> list[PontoDaLiga]:
    return PontoDaLiga.query.filter(PontoDaLiga.criado_em >= inicio.replace(tzinfo=None),
                                    PontoDaLiga.criado_em < fim.replace(tzinfo=None)).all()


def placar(inicio: datetime, fim: datetime) -> list[dict[str, Any]]:
    por_setor: dict[str, dict[str, Any]] = defaultdict(lambda: {"pontos": 0, "por_tipo": defaultdict(int)})
    for setor in {setor_da_camera(c) for c in Camera.query.all()}:
        por_setor[setor]  # setor sem ponto aparece com zero (não some da liga)
    for p in _pontos_entre(inicio, fim):
        por_setor[p.setor]["pontos"] += p.pontos
        por_setor[p.setor]["por_tipo"][p.tipo] += 1
    linhas = [{"setor": s, "pontos": d["pontos"], "por_tipo": dict(d["por_tipo"])} for s, d in por_setor.items()]
    return sorted(linhas, key=lambda x: (-x["pontos"], x["setor"]))


def desativar_missao(missao: Missao, agora: datetime | None = None) -> None:
    """Exclusão lógica: some da Liga e do turno atual, mas guarda QUANDO, para a retrospectiva
    continuar contando os turnos em que a missão valia (apagar hoje não reescreve o passado)."""
    missao.ativa = False
    missao.desativada_em = missao.desativada_em or agora or datetime.now(timezone.utc)
    db.session.commit()


def missao_valia_no_turno(missao: Missao, inicio: datetime, fim: datetime) -> bool:
    """A missão existia em algum momento do turno [inicio, fim).

    Criada depois do fim do turno: não vale (missão nova não cumpre turno antigo).
    Apagada antes do início: não vale. Apagada sem data (antes da coluna existir): fica de fora, como antes.
    """
    if _utc(missao.criado_em) >= fim:
        return False
    if missao.ativa:
        return True
    return missao.desativada_em is not None and _utc(missao.desativada_em) > inicio


def progresso_da_missao(missao: Missao, inicio: datetime, fim: datetime, pontos: list[PontoDaLiga]) -> dict[str, Any]:
    limite = fim
    if missao.ate_hora:
        local_inicio = inicio.astimezone()
        corte = datetime.combine(local_inicio.date(), _hora(missao.ate_hora), tzinfo=local_inicio.tzinfo)
        if corte < local_inicio:
            corte += timedelta(days=1)
        limite = min(fim, corte.astimezone(timezone.utc))
    tipos = {"reconhecido_rapido": ("reconhecido_rapido",)}.get(missao.tipo, (missao.tipo,))
    feitos = sum(
        1 for p in pontos
        if p.tipo in tipos and (missao.setor is None or p.setor == missao.setor)
        and _utc(p.criado_em) < limite
    )
    return missao.to_dict() | {"feito": feitos, "cumprida": feitos >= missao.alvo,
                               "progresso": round(min(1.0, feitos / max(1, missao.alvo)), 3)}


def estado(agora: datetime | None = None, turnos: str = "06:00-14:00,14:00-22:00,22:00-06:00") -> dict[str, Any]:
    agora = agora or datetime.now(timezone.utc)
    t_inicio, t_fim = temporada(agora)
    t = turno(agora, turnos)
    xp = db.session.query(db.func.coalesce(db.func.sum(PontoDaLiga.pontos), 0)).scalar() or 0
    pontos_do_turno = _pontos_entre(t["inicio"], t["fim"])
    missoes = [progresso_da_missao(m, t["inicio"], t["fim"], pontos_do_turno)
               for m in Missao.query.filter_by(ativa=True).order_by(Missao.id).all()]
    semana_iso = t_inicio.astimezone().isocalendar()
    return {
        "temporada": {"inicio": t_inicio.isoformat(), "fim": t_fim.isoformat(), "semana": semana_iso[1], "ano": semana_iso[0]},
        "setores": placar(t_inicio, t_fim),
        "planta": nivel(int(xp)),
        "turno": {"nome": t["nome"], "inicio": t["inicio"].isoformat(), "fim": t["fim"].isoformat()},
        "missoes": missoes,
        "pontos": PONTOS,
        "rotulos": ROTULOS,
    }
