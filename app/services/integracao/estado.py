"""Estado da planta para a camada industrial: torre sinalizadora e sirene.

Função PURA: recebe um resumo por câmera (o `MonitorService` monta) e devolve o
que um CLP, um SCADA ou um broker MQTT consome. Nada de I/O, relógio global ou
acesso ao banco: o instante vem por parâmetro, então o teste é determinístico.

Regras da torre (a de cima vence):

- VERMELHO: algum incidente CRÍTICO ativo, ou câmera com a visão comprometida
  (obstruída/movida: a planta ficou cega naquele ponto, e "sem alerta" deixa
  de significar "sem risco");
- AMARELO: incidente não crítico ativo, câmera offline ou visão degradada;
- VERDE: o resto.

Entrada por câmera (campos extras são ignorados; ausentes viram o neutro):

    id, nome, estado ("ok"|"atencao"|"alarme"|"offline"),
    incidentes_por_regra {regra: n}, conformidade 0-1 | None,
    ultimo_alerta {"mensagem", "severidade", "ts"} | None, saude_visual str,
    incidentes_criticos int  (opcional: quantos dos incidentes ativos são críticos),
    critico_nao_reconhecido bool,
    escalonado bool  (crítico sem reconhecimento além do prazo da TV; ver app/services/escalonamento.py.
                      Só repassado: a cor da torre continua a regra abaixo, a UI usa o campo para piscar)

Quando `incidentes_criticos` não vem, a câmera em `estado == "alarme"` conta como
crítica: é o único estado que o motor já classifica como alarme.

`saude_visual` não tem vocabulário fechado no motor. Casamos por prefixo, sem
acento: "obstru*" e "mov*" derrubam a torre para vermelho; "degrad*", "desfoc*"
, "escur*" e "ofusc*" para amarelo. Qualquer outro valor (inclusive "ok", "normal") é neutro.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

TORRE_VERDE = "verde"
TORRE_AMARELO = "amarelo"
TORRE_VERMELHO = "vermelho"

_VISAO_CEGA = ("obstru", "mov")
_VISAO_DEGRADADA = ("degrad", "desfoc", "escur", "ofusc")


def _normalizar(texto: Any) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


def _inteiro_nao_negativo(valor: Any) -> int:
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _conformidade(valor: Any) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return min(1.0, max(0.0, float(valor)))
    except (TypeError, ValueError):
        return None


def _normalizar_camera(bruta: dict[str, Any]) -> dict[str, Any]:
    incidentes = {str(regra): _inteiro_nao_negativo(n) for regra, n in (bruta.get("incidentes_por_regra") or {}).items()}
    estado = _normalizar(bruta.get("estado")) or "ok"
    if "incidentes_criticos" in bruta:
        criticos = _inteiro_nao_negativo(bruta["incidentes_criticos"])
    else:
        criticos = (sum(incidentes.values()) or 1) if estado == "alarme" else 0
    return {
        "id": bruta.get("id"),
        "nome": str(bruta.get("nome") or bruta.get("id") or ""),
        "estado": estado,
        "incidentes_por_regra": incidentes,
        "incidentes_criticos": criticos,
        "conformidade": _conformidade(bruta.get("conformidade")),
        "ultimo_alerta": bruta.get("ultimo_alerta") or None,
        "saude_visual": str(bruta.get("saude_visual") or ""),
        "critico_nao_reconhecido": bool(bruta.get("critico_nao_reconhecido")),
        "escalonado": bool(bruta.get("escalonado")),
    }


def _torre_da_camera(camera: dict[str, Any]) -> str:
    saude = _normalizar(camera["saude_visual"])
    if camera["incidentes_criticos"] > 0 or saude.startswith(_VISAO_CEGA):
        return TORRE_VERMELHO
    if sum(camera["incidentes_por_regra"].values()) > 0 or camera["estado"] in ("atencao", "offline") or saude.startswith(_VISAO_DEGRADADA):
        return TORRE_AMARELO
    return TORRE_VERDE


def estado_da_planta(cameras: list[dict[str, Any]], agora: datetime | None = None) -> dict[str, Any]:
    """Resume as câmeras em `{planta_em_alarme, torre, sirene, cameras, ts}`.

    `planta_em_alarme` é `torre == "vermelho"`; amarelo é atenção, não alarme.
    `sirene` exige torre vermelha E algum alerta crítico ainda não reconhecido:
    reconhecer o alerta silencia a sirene, a torre continua vermelha até o
    incidente acabar.
    """
    normalizadas = [_normalizar_camera(c) for c in cameras or []]
    ordem = {TORRE_VERDE: 0, TORRE_AMARELO: 1, TORRE_VERMELHO: 2}
    torre = TORRE_VERDE
    for camera in normalizadas:
        parcial = _torre_da_camera(camera)
        if ordem[parcial] > ordem[torre]:
            torre = parcial
    sirene = torre == TORRE_VERMELHO and any(c["critico_nao_reconhecido"] for c in normalizadas)
    instante = agora or datetime.now(timezone.utc)
    return {
        "planta_em_alarme": torre == TORRE_VERMELHO,
        "torre": torre,
        "sirene": sirene,
        "cameras": normalizadas,
        "ts": instante.isoformat(),
    }
