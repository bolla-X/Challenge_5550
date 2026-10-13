"""Estatísticas do pipeline de UMA câmera, sempre ligadas e baratas.

O `PROFILE_FRAMES` que já existia responde "onde está o tempo" num log a cada N
frames, mas só quando alguém lembra de ligar — e média esconde cauda. Isto aqui
guarda as últimas amostras de cada etapa em `deque` de tamanho fixo e devolve
p50/p95/p99 sob demanda. O custo por amostra é um `append` (atômico no CPython,
sem lock) e a memória é limitada pelo `maxlen`, então pode ficar ligado em
produção e alimentar o painel de diagnóstico e o `scripts/bench.py`.

Duas famílias de dado:

- **duração** (ms) por etapa: captura, inferência, encode... → percentis;
- **contador** com instante: frames lidos, publicados, descartados, bytes
  enviados... → taxa por segundo numa janela.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

# 1.800 amostras = 2 min a 15 fps. Cobre a janela de 60 s do bench com folga.
AMOSTRAS_POR_ETAPA = 1800
EVENTOS_POR_CONTADOR = 20000


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil por interpolação linear (mesmo método do `numpy.percentile`)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    pos = (len(ordenados) - 1) * (p / 100.0)
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (pos - baixo)


class EstatisticasDoPipeline:
    def __init__(self, *, amostras: int = AMOSTRAS_POR_ETAPA) -> None:
        self._amostras = amostras
        self._duracoes: dict[str, deque[tuple[float, float]]] = {}
        self._contadores: dict[str, deque[tuple[float, int]]] = {}
        self._totais: dict[str, int] = {}

    def duracao(self, etapa: str, ms: float, *, agora: float | None = None) -> None:
        fila = self._duracoes.get(etapa)
        if fila is None:
            fila = self._duracoes.setdefault(etapa, deque(maxlen=self._amostras))
        fila.append((time.monotonic() if agora is None else agora, float(ms)))

    def contar(self, nome: str, n: int = 1, *, agora: float | None = None) -> None:
        fila = self._contadores.get(nome)
        if fila is None:
            fila = self._contadores.setdefault(nome, deque(maxlen=EVENTOS_POR_CONTADOR))
        fila.append((time.monotonic() if agora is None else agora, int(n)))
        self._totais[nome] = self._totais.get(nome, 0) + int(n)

    def limpar(self) -> None:
        self._duracoes.clear()
        self._contadores.clear()
        self._totais.clear()

    def resumo(self, janela_s: float = 30.0) -> dict[str, Any]:
        agora = time.monotonic()
        limite = agora - janela_s
        etapas: dict[str, dict[str, float | int | None]] = {}
        for etapa, fila in list(self._duracoes.items()):
            valores = [ms for instante, ms in list(fila) if instante >= limite]
            if not valores:
                continue
            etapas[etapa] = {
                "n": len(valores),
                "media": round(sum(valores) / len(valores), 3),
                "p50": _arredondar(percentil(valores, 50)),
                "p95": _arredondar(percentil(valores, 95)),
                "p99": _arredondar(percentil(valores, 99)),
                "max": round(max(valores), 3),
            }
        taxas: dict[str, float] = {}
        for nome, fila in list(self._contadores.items()):
            eventos = [(instante, n) for instante, n in list(fila) if instante >= limite]
            if not eventos:
                taxas[nome] = 0.0
                continue
            # Divide pela janela efetivamente coberta: logo depois do start a
            # janela está parcial e dividir pelos 30 s inteiros subestimaria.
            coberto = max(1e-6, min(janela_s, agora - eventos[0][0]))
            taxas[nome] = round(sum(n for _, n in eventos) / coberto, 3)
        return {"janela_s": janela_s, "etapas": etapas, "taxas_por_s": taxas, "totais": dict(self._totais)}


def _arredondar(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 3)
