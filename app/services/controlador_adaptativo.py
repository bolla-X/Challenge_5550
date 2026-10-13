"""Controlador adaptativo ("modo batata"): degrada com limite, histerese e volta.

Numa máquina fraca o modelo não dá conta de todas as câmeras no ritmo pedido.
Sem controle, o sintoma é invisível e perigoso: a análise envelhece (o alerta
chega segundos depois do fato) enquanto o vídeo continua fluido e "parece"
que está tudo bem. Este controlador mede a IDADE do quadro no momento em que
ele é inferido (`idade_na_inferencia`, p95 em janela curta) e, quando ela
passa do limite, reduz carga em degraus, sempre na mesma ordem e sempre
avisando o operador o que foi reduzido:

1. detectar a cada N+1 quadros (até `n_max`) — o vídeo segue no FPS da fonte;
2. pose a cada K inferências (até `pose_k_max`), quando a pose é YOLO;
3. telemetria do painel pela metade (menos eventos por segundo no socket).

A resolução do modelo NUNCA entra na escada: 640 é a referência do guarda de
qualidade e toda resolução menor foi reprovada nele (512: 72 %, 416: 64 %,
capacete a 8 % — docs/NEXT2026/CHANGELOG.md §4.3). Reduzir imgsz sob carga
trocaria atraso por cegueira, justamente quando a máquina está apertada.

Histerese: degrada só depois de `ticks_para_degradar` leituras seguidas acima
do limite alto, e recupera um degrau só depois de `ticks_para_recuperar`
leituras seguidas abaixo do limite baixo. A banda morta entre os dois limites
evita que o sistema oscile entre níveis a cada tique.

A decisão (`avaliar`) é função pura do estado + métrica, testada em
tests/test_controlador_adaptativo.py; quem aplica é o `MonitorService`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EstadoAdaptativo:
    nivel: int = 0
    acima: int = 0
    abaixo: int = 0
    motivo: str | None = None


@dataclass
class ControladorAdaptativo:
    n_base: int = 1
    n_max: int = 6
    pose_k_max: int = 1
    telemetria_base_hz: float = 8.0
    limite_alto_ms: float = 1500.0
    limite_baixo_ms: float = 600.0
    ticks_para_degradar: int = 3
    ticks_para_recuperar: int = 5
    estado: EstadoAdaptativo = field(default_factory=EstadoAdaptativo)

    # ---------------------------------------------------------------- níveis
    def degraus(self) -> list[dict[str, Any]]:
        """A escada de degradação, do nível 0 (nada reduzido) ao máximo."""
        escada: list[dict[str, Any]] = [
            {"n": self.n_base, "pose_k": 1, "telemetria_hz": self.telemetria_base_hz}
        ]
        n = self.n_base
        while n < self.n_max:
            n += 1
            escada.append(escada[-1] | {"n": n})
        for k in range(2, self.pose_k_max + 1):
            escada.append(escada[-1] | {"pose_k": k})
        escada.append(escada[-1] | {"telemetria_hz": max(1.0, self.telemetria_base_hz / 2)})
        return escada

    @property
    def nivel_max(self) -> int:
        return len(self.degraus()) - 1

    def configuracao(self, nivel: int | None = None) -> dict[str, Any]:
        degraus = self.degraus()
        return degraus[max(0, min(len(degraus) - 1, self.estado.nivel if nivel is None else nivel))]

    def reducoes(self) -> list[str]:
        """O que está reduzido AGORA, em texto para o banner do operador."""
        atual, base = self.configuracao(), self.configuracao(0)
        textos = []
        if atual["n"] != base["n"]:
            textos.append(f"detecção a cada {atual['n']} quadros (era {base['n']})")
        if atual["pose_k"] != base["pose_k"]:
            textos.append(f"pose a cada {atual['pose_k']} análises (era a cada análise)")
        if atual["telemetria_hz"] != base["telemetria_hz"]:
            textos.append(f"painel atualiza {atual['telemetria_hz']:g}x/s (era {base['telemetria_hz']:g})")
        return textos

    # --------------------------------------------------------------- decisão
    def avaliar(self, idade_p95_ms: float | None) -> bool:
        """Lê uma métrica nova; devolve True se o nível MUDOU."""
        est = self.estado
        if idade_p95_ms is None:
            # Sem inferência na janela (câmeras paradas): não decide nada.
            est.acima = est.abaixo = 0
            return False
        if idade_p95_ms > self.limite_alto_ms:
            est.acima += 1
            est.abaixo = 0
            if est.acima >= self.ticks_para_degradar and est.nivel < self.nivel_max:
                est.nivel += 1
                est.acima = 0
                est.motivo = f"análise atrasada: p95 {idade_p95_ms:.0f} ms > {self.limite_alto_ms:.0f} ms"
                return True
        elif idade_p95_ms < self.limite_baixo_ms:
            est.abaixo += 1
            est.acima = 0
            if est.abaixo >= self.ticks_para_recuperar and est.nivel > 0:
                est.nivel -= 1
                est.abaixo = 0
                est.motivo = f"carga normalizada: p95 {idade_p95_ms:.0f} ms < {self.limite_baixo_ms:.0f} ms"
                return True
        else:
            # Banda morta: nem degrada nem recupera, e zera as duas contagens.
            est.acima = est.abaixo = 0
        return False

    def resumo(self) -> dict[str, Any]:
        return {
            "nivel": self.estado.nivel,
            "nivel_max": self.nivel_max,
            "degradado": self.estado.nivel > 0,
            "reducoes": self.reducoes(),
            "motivo": self.estado.motivo,
            "configuracao": self.configuracao(),
            "limites_ms": {"alto": self.limite_alto_ms, "baixo": self.limite_baixo_ms},
        }
