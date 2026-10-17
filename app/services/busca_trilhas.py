"""Busca nas trilhas gravadas (M6): filtros determinísticos, sem LLM.

Lê os registros de `app/services/trilhas.py` (uma linha por análise, uma entrada por
pessoa rastreada) e devolve TRECHOS CONTÍNUOS de um rótulo de rastreio que atendem a
todos os filtros ao mesmo tempo. O rótulo é "Pessoa N": número de rastreio por
posição, NUNCA identidade (ver docs/NEXT2026/GLOSSARIO.md).

Semântica dos filtros (todas valem juntas, amostra a amostra):

- zona: o CENTRO da caixa está dentro do polígono da área de risco (o mesmo ponto que a
  regra de alerta e o simulador usam), com o ponto-em-polígono de `aproximacao.py`;
- EPI ausente: PELO MENOS UM dos EPIs pedidos está ausente na amostra;
- velocidade: deslocamento dos PÉS entre duas amostras consecutivas do mesmo ID, em
  fração do quadro por segundo. A primeira amostra de uma presença não tem velocidade e
  não passa num filtro de velocidade;
- permanência mínima: duração do trecho contínuo (último instante menos o primeiro).

Um trecho acaba quando uma amostra deixa de atender ao filtro ou quando o ID some por
mais de `lacuna_s` (a mesma tolerância de `EstimadorDeAproximacao.validade_s`).
Função pura dos registros e dos filtros: não toca em banco, arquivo nem relógio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.services.aproximacao import ponto_no_poligono
from app.services.trilhas import numero
from app.vision.person_compliance_matcher import PPE_KEYS

Ponto = tuple[float, float]

MAX_PONTOS = 200
# Estados gravados na trilha (`trilhas._codigo`) e os nomes que a API aceita para "ausente".
_AUSENTE = frozenset({"m", "missing", "ausente"})


@dataclass(frozen=True)
class Filtros:
    de: float | None = None
    ate: float | None = None
    zona: tuple[Ponto, ...] | None = None  # None = sem filtro de zona
    permanencia_min_s: float = 0.0
    epi_ausente: frozenset[str] = frozenset()
    vel_min: float | None = None
    vel_max: float | None = None
    lacuna_s: float = 6.0


@dataclass
class _Trecho:
    pontos: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, t) dos pés
    epis_ausentes: set[str] = field(default_factory=set)
    soma_vel: float = 0.0
    n_vel: int = 0


@dataclass
class _Presenca:
    ultimo: tuple[float, float, float] | None = None  # (t, pe_x, pe_y)
    trecho: _Trecho | None = None


def rotulo_de(rastreio: Any) -> str:
    return f"Pessoa {rastreio}"


def amostrar(pontos: list, maximo: int = MAX_PONTOS) -> list:
    """No máximo `maximo` pontos, espaçados por igual e SEMPRE com o primeiro e o último."""
    n = len(pontos)
    if n <= maximo:
        return list(pontos)
    maximo = max(2, maximo)
    return [pontos[round(i * (n - 1) / (maximo - 1))] for i in range(maximo)]


def _ausente(estado: Any) -> bool:
    return str(estado) in _AUSENTE


def _casa(f: Filtros, zona: list[Ponto] | None, centro: Ponto, epis: dict[str, Any], vel: float | None) -> bool:
    if zona is not None and not ponto_no_poligono(centro, zona):
        return False
    if f.epi_ausente and not any(_ausente(epis.get(chave)) for chave in f.epi_ausente):
        return False
    if f.vel_min is not None and (vel is None or vel < f.vel_min):
        return False
    if f.vel_max is not None and (vel is None or vel > f.vel_max):
        return False
    return True


def _fechar(f: Filtros, camera_id: int | None, rastreio: Any, trecho: _Trecho | None, saida: list[dict[str, Any]]) -> None:
    if trecho is None or not trecho.pontos:
        return
    inicio, fim = trecho.pontos[0][2], trecho.pontos[-1][2]
    if fim - inicio < f.permanencia_min_s:
        return
    saida.append({
        "camera_id": camera_id,
        "rotulo": rotulo_de(rastreio),
        "rastreio": rastreio,
        "inicio": inicio,
        "fim": fim,
        "duracao_s": round(fim - inicio, 1),
        "epis_ausentes": [k for k in PPE_KEYS if k in trecho.epis_ausentes],
        "velocidade_media": round(trecho.soma_vel / trecho.n_vel, 4) if trecho.n_vel else None,
        "total_pontos": len(trecho.pontos),
        "pontos": [[round(x, 4), round(y, 4), t] for x, y, t in amostrar(trecho.pontos)],
        "alerta_id": None,
        "incidente_id": None,
        "clipe_da_mesma_pessoa": None,
    })


def buscar(registros: Iterable[dict[str, Any]], filtros: Filtros, *, camera_id: int | None = None) -> list[dict[str, Any]]:
    """Trechos contínuos que atendem aos filtros, do mais recente para o mais antigo.

    `registros` em ordem de tempo (como `GravadorDeTrilhas.ler`). Linha malformada é ignorada.
    """
    zona = list(filtros.zona) if filtros.zona is not None else None
    presencas: dict[Any, _Presenca] = {}
    saida: list[dict[str, Any]] = []
    for registro in registros:
        try:
            t = float(registro["t"])
        except (KeyError, TypeError, ValueError):
            continue
        if (filtros.de is not None and t < filtros.de) or (filtros.ate is not None and t > filtros.ate):
            continue
        for linha in registro.get("p") or []:
            try:
                rastreio, pe_x, pe_y, cx, cy, epis = linha[:6]
                pe_x, pe_y, cx, cy = float(pe_x), float(pe_y), float(cx), float(cy)
            except (TypeError, ValueError):
                continue
            presenca = presencas.setdefault(rastreio, _Presenca())
            vel: float | None = None
            if presenca.ultimo is not None:
                dt = t - presenca.ultimo[0]
                if dt > filtros.lacuna_s:  # sumiu e voltou: é outro trecho
                    _fechar(filtros, camera_id, rastreio, presenca.trecho, saida)
                    presenca.trecho = presenca.ultimo = None
                elif dt <= 0:  # mesmo instante repetido: não dá velocidade
                    continue
                else:
                    vel = math.hypot(pe_x - presenca.ultimo[1], pe_y - presenca.ultimo[2]) / dt
            presenca.ultimo = (t, pe_x, pe_y)
            epis = epis if isinstance(epis, dict) else {}
            if _casa(filtros, zona, (cx, cy), epis, vel):
                if presenca.trecho is None:
                    presenca.trecho = _Trecho()
                trecho = presenca.trecho
                trecho.pontos.append((pe_x, pe_y, t))
                trecho.epis_ausentes.update(k for k, v in epis.items() if _ausente(v))
                if vel is not None:
                    trecho.soma_vel += vel
                    trecho.n_vel += 1
            else:
                _fechar(filtros, camera_id, rastreio, presenca.trecho, saida)
                presenca.trecho = None
    for rastreio, presenca in presencas.items():
        _fechar(filtros, camera_id, rastreio, presenca.trecho, saida)
    return sorted(saida, key=lambda r: (-r["fim"], -r["inicio"], r["rotulo"]))


# ------------------------------------------------------- clipe de replay ---
@dataclass(frozen=True)
class AlertaDaBusca:
    """O que a busca precisa saber de um alerta para ligar um trecho ao replay dele."""

    id: int
    t: float  # epoch s de criação
    rastreio: Any  # número de rastreio do alerta (None se o alerta não é de uma pessoa)
    incidente_id: int | None = None


def associar_clipes(
    resultados: list[dict[str, Any]],
    alertas: Iterable[AlertaDaBusca],
    tem_clipe: Callable[[int], bool],
    *,
    margem_s: float = 10.0,
) -> list[dict[str, Any]]:
    """Preenche `alerta_id`, `incidente_id` e `clipe_da_mesma_pessoa` de cada trecho.

    Candidato: alerta criado entre `inicio - margem_s` e `fim + margem_s` que TEM clipe
    de replay (`tem_clipe`). Vence o do mesmo rótulo de rastreio e, entre iguais, o mais
    próximo do início do trecho. Sem candidato, os três campos ficam como estavam.
    """
    candidatos = sorted(alertas, key=lambda a: a.t)
    com_clipe: dict[int, bool] = {}

    def clipe(alerta_id: int) -> bool:
        if alerta_id not in com_clipe:
            com_clipe[alerta_id] = bool(tem_clipe(alerta_id))
        return com_clipe[alerta_id]

    saida = []
    for r in resultados:
        no_periodo = [a for a in candidatos if r["inicio"] - margem_s <= a.t <= r["fim"] + margem_s]
        no_periodo = [a for a in no_periodo if clipe(a.id)]
        if not no_periodo:
            saida.append(r)
            continue
        melhor = min(no_periodo, key=lambda a: (numero(a.rastreio) != numero(r["rastreio"]), abs(a.t - r["inicio"])))
        saida.append(r | {
            "alerta_id": melhor.id,
            "incidente_id": melhor.incidente_id,
            "clipe_da_mesma_pessoa": numero(melhor.rastreio) == numero(r["rastreio"]),
        })
    return saida
