"""Linha causal do incidente (X4, MISSÃO 2): uma narrativa determinística, sem LLM.

Exemplo do que sai, por ID de rastreio:

    13:02:10 aproximou-se da Zona A (projeção ~4 s)
    13:02:14 entrou na Zona A sem capacete
    → permaneceu 38 s
    13:02:52 postura de risco
    → alerta reconhecido em 6 s

Fontes, todas persistidas (sobrevivem a reinício): os eventos de aproximação
(F3, `approach_risk_area`), os alertas da pessoa naquela câmera (criação e
resolução) e o reconhecimento do incidente. Cada passo traz o alerta cujo
clipe cobre aquele instante, para a tela abrir o replay no quadro certo.

Só o que foi registrado vira frase: sem inferir intenção, sem "porque".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.risk_rules import PPE_RULES

# Janela do clipe em volta da criação do alerta (app/services/replay.py).
CLIPE_ANTES_S = 5.0
CLIPE_DEPOIS_S = 3.0

FRASE_DE_OUTRAS_REGRAS = {
    "fall_detected": "possível queda",
    "fallen_person": "possível queda",
    "suspicious_posture": "postura de risco",
    "sos_gesto": "gesto de socorro",
    "ergonomia_tronco": "flexão do tronco acima de 45°",
    "pessoa_imovel": "imóvel na zona",
}


def _ts(valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, datetime):
        dt = valor
    else:
        dt = datetime.fromisoformat(str(valor))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _pessoa(alerta: dict[str, Any]) -> Any:
    pid = (alerta.get("metadata") or {}).get("person_id")
    if isinstance(pid, str) and pid.startswith("person_") and pid[7:].isdigit():
        return int(pid[7:])
    return pid


def _sem(feature: str | None) -> str:
    return PPE_RULES.get(feature or "", ("sem EPI", ""))[0].lower()


def _lista_sem(itens: list[str]) -> str:
    """["sem capacete", "sem colete", "sem luvas"] → "sem capacete, colete e luvas"."""
    nomes = [i.removeprefix("sem ").strip() for i in itens]
    if len(nomes) == 1:
        return f"sem {nomes[0]}"
    return f"sem {', '.join(nomes[:-1])} e {nomes[-1]}"


def _duracao(segundos: float) -> str:
    s = int(round(segundos))
    return f"{s} s" if s < 90 else f"{s // 60} min {s % 60:02d} s"


def _alerta_do_quadro(t: float, alertas: list[dict[str, Any]]) -> int | None:
    """O alerta cujo clipe cobre `t`; senão, o de criação mais próxima."""
    melhor, distancia = None, None
    for a in alertas:
        c = _ts(a.get("created_at"))
        if c is None:
            continue
        if c - CLIPE_ANTES_S <= t <= c + CLIPE_DEPOIS_S:
            return a["id"]
        d = abs(c - t)
        if distancia is None or d < distancia:
            melhor, distancia = a["id"], d
    return melhor


def montar(incidente: dict[str, Any], alertas: list[dict[str, Any]], eventos: list[dict[str, Any]],
           agora: float) -> dict[str, Any]:
    """`alertas`: da câmera do incidente, na janela dele; `eventos`: de aproximação da câmera."""
    zona = incidente.get("zona") or "zona de risco"
    zona_frase = zona if zona not in ("Fora da zona", "Toda a câmera") else "zona de risco"
    pessoas = list(incidente.get("pessoas") or [])
    reconhecido = incidente.get("reconhecido_em_s")
    linhas: dict[str, list[dict[str, Any]]] = {}
    for pid in pessoas:
        da_pessoa = sorted((a for a in alertas if _pessoa(a) == pid), key=lambda a: _ts(a.get("created_at")) or 0)
        passos: list[dict[str, Any]] = []

        def passo(t: float | None, texto: str, tipo: str, *, duracao: bool = False,
                  da_pessoa: list[dict[str, Any]] = da_pessoa, passos: list[dict[str, Any]] = passos) -> None:
            if t is None:
                return
            passos.append({"t": round(t, 3), "texto": texto, "tipo": tipo, "duracao": duracao,
                           "alert_id": _alerta_do_quadro(t, da_pessoa)})

        # 1) Aproximação (F3): o registro mais recente ANTES da primeira violação.
        primeira = _ts(da_pessoa[0].get("created_at")) if da_pessoa else None
        aproximacoes = [e for e in eventos if (e.get("metadata") or {}).get("track_id") == pid
                        and primeira is not None and (_ts(e.get("created_at")) or 0) <= primeira]
        if aproximacoes:
            e = max(aproximacoes, key=lambda x: _ts(x.get("created_at")) or 0)
            segundos = (e.get("metadata") or {}).get("segundos_ate_entrar")
            passo(_ts(e.get("created_at")), f"aproximou-se da {zona_frase}"
                  + (f" (projeção ~{float(segundos):.0f} s)" if segundos is not None else ""), "aproximacao")

        # 2) Entrada / violação: a regra do incidente, com o EPI que faltava naquele instante.
        do_incidente = [a for a in da_pessoa if a.get("rule") == incidente.get("rule")]
        principal = do_incidente[0] if do_incidente else (da_pessoa[0] if da_pessoa else None)
        if principal is not None:
            t0 = _ts(principal.get("first_seen_at") or principal.get("created_at"))
            faltando = sorted({
                _sem(a.get("feature")) for a in da_pessoa
                if str(a.get("rule", "")).startswith("missing_") and a is not principal
                and (_ts(a.get("created_at")) or 0) <= (t0 or 0) + 2.0
                and (_ts(a.get("resolved_at")) or agora) >= (t0 or 0)
            })
            if principal.get("rule") == "risk_area_presence":
                texto = f"entrou na {zona_frase}" + (f" {_lista_sem(faltando)}" if faltando else "")
            else:
                onde = f"estava na {zona}" if zona not in ("Fora da zona", "Toda a câmera") else "apareceu"
                texto = f"{onde} {_sem(principal.get('feature'))}"
            passo(t0, texto, "violacao")
            # 3) Quanto tempo ficou assim.
            fim = _ts(principal.get("resolved_at"))
            if fim is not None and t0 is not None:
                passo(fim, f"permaneceu {_duracao(fim - t0)}", "permanencia", duracao=True)
            elif t0 is not None:
                passo(agora, f"continua há {_duracao(agora - t0)}", "permanencia", duracao=True)

        # 4) Outros sinais da mesma pessoa no período (postura, queda, SOS…).
        for a in da_pessoa:
            frase = FRASE_DE_OUTRAS_REGRAS.get(str(a.get("rule")))
            if frase:
                passo(_ts(a.get("created_at")), frase, "sinal")

        # 5) Reconhecimento humano do incidente.
        if reconhecido is not None:
            t_rec = _ts(incidente.get("reconhecido_em"))
            passo(t_rec, f"alerta reconhecido em {_duracao(float(reconhecido))}", "reconhecimento", duracao=True)

        passos.sort(key=lambda p: (p["t"], p["tipo"] == "reconhecimento"))
        linhas[str(pid)] = passos
    return {"incidente_id": incidente.get("id"), "pessoas": [str(p) for p in pessoas], "linhas": linhas}
