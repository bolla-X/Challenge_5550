"""Linha causal do incidente (X4): narrativa determinística a partir dos eventos do ID."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.linha_causal import montar

T0 = datetime(2026, 10, 14, 13, 2, 10, tzinfo=timezone.utc)


def iso(segundos: float) -> str:
    return (T0 + timedelta(seconds=segundos)).isoformat()


def alerta(aid, regra, feature, criado, resolvido=None, pessoa="person_4"):
    return {"id": aid, "rule": regra, "feature": feature, "created_at": iso(criado), "first_seen_at": iso(criado),
            "resolved_at": iso(resolvido) if resolvido is not None else None, "metadata": {"person_id": pessoa}}


INCIDENTE = {"id": 9, "rule": "risk_area_presence", "zona": "Zona A", "pessoas": [4],
             "reconhecido_em": iso(10), "reconhecido_em_s": 6.0}
ALERTAS = [
    alerta(1, "risk_area_presence", "risk_area", 4, resolvido=42),
    alerta(2, "missing_helmet", "helmet", 4.5, resolvido=60),
    alerta(3, "suspicious_posture", "posture", 42),
    alerta(4, "missing_helmet", "helmet", 5, pessoa="person_8"),  # outra pessoa: fica fora
]
EVENTOS = [{"created_at": iso(0), "metadata": {"track_id": 4, "segundos_ate_entrar": 4.2}}]


def test_narrativa_do_exemplo_da_missao():
    r = montar(INCIDENTE, ALERTAS, EVENTOS, agora=T0.timestamp() + 100)
    passos = r["linhas"]["4"]
    textos = [p["texto"] for p in passos]
    assert textos == [
        "aproximou-se da Zona A (projeção ~4 s)",
        "entrou na Zona A sem capacete",
        "incidente reconhecido em 6 s",
        "permaneceu 38 s",
        "postura de risco",
    ]
    assert [p["t"] for p in passos] == sorted(p["t"] for p in passos)


def test_cada_passo_aponta_o_alerta_do_replay():
    passos = montar(INCIDENTE, ALERTAS, EVENTOS, agora=T0.timestamp() + 100)["linhas"]["4"]
    por_tipo = {p["tipo"]: p for p in passos}
    assert por_tipo["violacao"]["alert_id"] == 1  # clipe do alerta 1 cobre 4 s
    assert por_tipo["sinal"]["alert_id"] == 3
    assert all(p["alert_id"] in (1, 2, 3) for p in passos)


def test_deterministica():
    a = montar(INCIDENTE, ALERTAS, EVENTOS, agora=T0.timestamp() + 100)
    b = montar(INCIDENTE, list(reversed(ALERTAS)), EVENTOS, agora=T0.timestamp() + 100)
    assert a == b


def test_ainda_ativo_e_sem_aproximacao():
    inc = {"id": 1, "rule": "missing_vest", "zona": "Fora da zona", "pessoas": [4], "reconhecido_em_s": None}
    r = montar(inc, [alerta(5, "missing_vest", "vest", 0)], [], agora=T0.timestamp() + 30)
    assert [p["texto"] for p in r["linhas"]["4"]] == ["apareceu sem colete", "continua há 30 s"]


def test_varios_epis_faltando_viram_uma_lista():
    alertas = [alerta(1, "risk_area_presence", "risk_area", 4), alerta(2, "missing_helmet", "helmet", 4.2),
               alerta(3, "missing_vest", "vest", 4.4), alerta(4, "missing_gloves", "gloves", 4.6)]
    inc = INCIDENTE | {"reconhecido_em_s": None}
    textos = [p["texto"] for p in montar(inc, alertas, [], agora=T0.timestamp() + 10)["linhas"]["4"]]
    assert "entrou na Zona A sem capacete, colete e luvas" in textos
