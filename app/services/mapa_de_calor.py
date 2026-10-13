"""Mapa de calor de risco (F7): ONDE as violações acontecem, com janela temporal.

Cada análise nova soma, numa grade de células sobre o quadro, a posição dos
pés de quem está em violação de EPI ou dentro da zona de risco. O acumulado
decai exponencialmente (meia-vida configurável): o mapa mostra o turno
recente, não a semana inteira empilhada.

Custo: um array numpy pequeno (48×27 = 1.296 floats) por câmera; uma soma por
pessoa em violação; o decaimento é aplicado sob demanda, pelo tempo decorrido,
não a cada quadro.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any

import numpy as np


class MapaDeCalor:
    def __init__(self, *, colunas: int = 48, linhas: int = 27, meia_vida_s: float = 900.0) -> None:
        self.colunas, self.linhas = colunas, linhas
        self.meia_vida_s = meia_vida_s
        self._grade = np.zeros((linhas, colunas), dtype=np.float32)
        # O relógio começa no primeiro uso, no MESMO referencial de quem chama.
        self._ultimo: float | None = None
        self._eventos = 0
        self._lock = threading.Lock()

    def _decair(self, agora: float) -> None:
        if self._ultimo is None:
            self._ultimo = agora
            return
        dt = agora - self._ultimo
        if dt > 0:
            self._grade *= math.pow(0.5, dt / self.meia_vida_s)
            self._ultimo = agora

    def somar(self, pontos: list[tuple[float, float]], *, agora: float | None = None, peso: float = 1.0) -> None:
        """`pontos` normalizados (0..1). Fora do quadro é ignorado."""
        if not pontos:
            return
        agora = time.monotonic() if agora is None else agora
        with self._lock:
            self._decair(agora)
            for x, y in pontos:
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    continue
                c = min(self.colunas - 1, int(x * self.colunas))
                linha = min(self.linhas - 1, int(y * self.linhas))
                self._grade[linha, c] += peso
                self._eventos += 1

    def exportar(self, *, agora: float | None = None) -> dict[str, Any]:
        agora = time.monotonic() if agora is None else agora
        with self._lock:
            self._decair(agora)
            maximo = float(self._grade.max())
            grade = (self._grade / maximo).round(3).tolist() if maximo > 0 else self._grade.tolist()
        return {"colunas": self.colunas, "linhas": self.linhas, "meia_vida_s": self.meia_vida_s,
                "eventos": self._eventos, "maximo": round(maximo, 3), "grade": grade}

    def limpar(self) -> None:
        with self._lock:
            self._grade[:] = 0
            self._eventos = 0
            self._ultimo = None


def pes_em_risco(compliance_state: dict[str, Any] | None, frame_shape) -> list[tuple[float, float]]:
    """Pés (normalizados) de quem tem EPI ausente/incorreto ou está na zona de risco."""
    altura, largura = frame_shape[:2]
    pontos = []
    for pessoa in (compliance_state or {}).get("people", []) or []:
        ppe = pessoa.get("ppe") or {}
        violacao = any((item or {}).get("status") in ("missing", "incorrect") for item in ppe.values())
        na_zona = ((pessoa.get("risk_area") or {}).get("status") in ("inside", "dentro", "danger"))
        if not (violacao or na_zona):
            continue
        box = pessoa.get("box") or {}
        try:
            pontos.append(((box["x1"] + box["x2"]) / 2 / max(1, largura), box["y2"] / max(1, altura)))
        except (KeyError, TypeError):
            continue
    return pontos
