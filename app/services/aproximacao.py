"""Pré-alerta de aproximação da zona de risco — PROJEÇÃO CINEMÁTICA, não IA.

O alerta de área de risco existente dispara quando a pessoa JÁ entrou. Este
módulo olha um passo antes: com a posição dos pés de cada track ao longo do
tempo, estima a velocidade (média exponencial, para não reagir a uma caixa
que tremeu num quadro) e projeta em linha reta até a borda do polígono. Se o
tempo até a entrada for menor que `limite_s`, sai um aviso AMARELO de
"aproximação".

O rótulo é honesto de propósito: é física de ponto material sobre uma reta
(posição + velocidade × tempo), não previsão por modelo. Pessoa que desvia
não entra — e o aviso some sozinho quando a projeção deixa de cruzar a zona.

Tudo em coordenadas NORMALIZADAS do quadro (0..1), as mesmas do polígono.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Ponto = tuple[float, float]


def ponto_no_poligono(p: Ponto, poligono: list[Ponto]) -> bool:
    x, y = p
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


def tempo_ate_entrar(p: Ponto, v: Ponto, poligono: list[Ponto]) -> float | None:
    """Menor t > 0 em que p + v·t cruza a borda do polígono; None se não cruza."""
    px, py = p
    vx, vy = v
    melhor: float | None = None
    n = len(poligono)
    for i in range(n):
        ax, ay = poligono[i]
        bx, by = poligono[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        denominador = vx * ey - vy * ex
        if abs(denominador) < 1e-12:
            continue  # trajetória paralela à aresta
        t = ((ax - px) * ey - (ay - py) * ex) / denominador
        u = ((ax - px) * vy - (ay - py) * vx) / denominador
        if t > 0 and 0.0 <= u <= 1.0 and (melhor is None or t < melhor):
            melhor = t
    return melhor


@dataclass
class _Trilha:
    pos: Ponto
    t: float
    vel: Ponto = (0.0, 0.0)
    amostras: int = 1


@dataclass
class EstimadorDeAproximacao:
    limite_s: float = 3.0
    # Abaixo disto (fração do quadro por segundo) a pessoa está parada: sem
    # aviso — parado na borda não é "aproximando".
    velocidade_minima: float = 0.02
    suavizacao: float = 0.5
    amostras_minimas: int = 3
    validade_s: float = 2.0
    _trilhas: dict[int, _Trilha] = field(default_factory=dict)

    def reset(self) -> None:
        self._trilhas.clear()

    def atualizar(self, pessoas: list[tuple[int, Ponto]], agora: float) -> None:
        """`pessoas`: (track_id, ponto dos pés normalizado), uma vez por inferência."""
        for track_id, pos in pessoas:
            trilha = self._trilhas.get(track_id)
            if trilha is None or agora - trilha.t > self.validade_s:
                self._trilhas[track_id] = _Trilha(pos=pos, t=agora)
                continue
            dt = agora - trilha.t
            if dt <= 0:
                continue
            instantanea = ((pos[0] - trilha.pos[0]) / dt, (pos[1] - trilha.pos[1]) / dt)
            a = self.suavizacao
            trilha.vel = (a * instantanea[0] + (1 - a) * trilha.vel[0], a * instantanea[1] + (1 - a) * trilha.vel[1])
            trilha.pos, trilha.t = pos, agora
            trilha.amostras += 1
        for track_id in [k for k, v in self._trilhas.items() if agora - v.t > self.validade_s]:
            del self._trilhas[track_id]

    def velocidades(self) -> dict[int, Ponto]:
        """Velocidade suavizada dos pés (fração do quadro por segundo) de quem tem amostras suficientes."""
        return {tid: t.vel for tid, t in list(self._trilhas.items()) if t.amostras >= self.amostras_minimas}

    def avisos(self, poligono: list[Ponto]) -> list[dict]:
        """Um aviso por track que deve ENTRAR na zona em menos de `limite_s`."""
        if len(poligono) < 3:
            return []
        saida = []
        for track_id, trilha in self._trilhas.items():
            if trilha.amostras < self.amostras_minimas or ponto_no_poligono(trilha.pos, poligono):
                continue
            rapidez = (trilha.vel[0] ** 2 + trilha.vel[1] ** 2) ** 0.5
            if rapidez < self.velocidade_minima:
                continue
            t = tempo_ate_entrar(trilha.pos, trilha.vel, poligono)
            if t is not None and t <= self.limite_s:
                saida.append({
                    "track_id": track_id,
                    "segundos_ate_entrar": round(t, 1),
                    "velocidade": round(rapidez, 3),
                    "metodo": "projecao_cinematica",
                })
        return sorted(saida, key=lambda item: item["segundos_ate_entrar"])
