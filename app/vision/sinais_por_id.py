"""Sinais que dependem de DURAÇÃO, por ID de rastreio (PR3: G3, G4, G7).

O motor de regras (`app/services/risk_rules.py`) é função pura do quadro. Estes
três sinais só existem no tempo:

- G3 SOS por gesto: os dois punhos acima da cabeça por >= 3 s;
- G4 pessoa imóvel em zona de risco: o pé quase não se move por >= X s,
  dentro da zona — rotulado como "não é diagnóstico";
- G7 ergonomia (estimativa): flexão do tronco (quadril → ombros contra a
  vertical) acima de 45° por >= N s, com tempo acumulado acima de 45° e 60°.
  Não é RULA, REBA nem avaliação da NR-17.

Tudo é por ID de rastreio, nunca por identidade. O relógio é passado de fora
(`agora`, em segundos monotônicos), então os testes não dormem.

"Não verificável" (keypoint com baixa confiança, pessoa fora do quadro) NÃO
zera a contagem por até `TOLERANCIA_S`: a análise roda a ~1 Hz na CPU, e um
punho perdido num quadro não pode desfazer 2 s de gesto. Passado esse tempo
sem evidência, a contagem é descartada — não detectado não é ausente, mas
também não é presente.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.vision.schemas import PoseResult

VISIBILIDADE_MINIMA = 0.4
TOLERANCIA_S = 1.5
# ID que some por mais que isto é esquecido (o rastreador já o teria trocado).
ESQUECER_APOS_S = 10.0
NOMES_CABECA = ("nose", "left_eye", "right_eye", "left_ear", "right_ear")


def _ponto(pose: PoseResult, nome: str, frame_shape) -> tuple[float, float] | None:
    lm = pose.by_name(nome)
    if lm is None or lm.visibility < VISIBILIDADE_MINIMA or (lm.x == 0.0 and lm.y == 0.0):
        return None
    return pose.point_px(nome, frame_shape)


def bracos_erguidos(pose: PoseResult, frame_shape) -> bool | None:
    """Os dois punhos acima do ponto mais alto da cabeça visível.

    None quando não dá para verificar (punho ou cabeça sem confiança). Em
    pixels: y cresce para baixo, então "acima" é y menor.
    """
    esquerdo = _ponto(pose, "left_wrist", frame_shape)
    direito = _ponto(pose, "right_wrist", frame_shape)
    cabeca = [p for p in (_ponto(pose, n, frame_shape) for n in NOMES_CABECA) if p is not None]
    if esquerdo is None or direito is None or not cabeca:
        return None
    topo = min(p[1] for p in cabeca)
    return esquerdo[1] < topo and direito[1] < topo


def flexao_do_tronco(pose: PoseResult, frame_shape) -> float | None:
    """Ângulo, em graus, entre o vetor quadril → ombros e a vertical para cima.

    0° = tronco ereto; 90° = tronco horizontal. Estimativa 2D: inclinação na
    direção da câmera aparece menor do que é.
    """
    ls, rs, lh, rh = (_ponto(pose, n, frame_shape) for n in ("left_shoulder", "right_shoulder", "left_hip", "right_hip"))
    if ls is None or rs is None or lh is None or rh is None:
        return None
    ombro = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
    quadril = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
    dx, dy = ombro[0] - quadril[0], quadril[1] - ombro[1]  # dy > 0: ombro acima do quadril
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(abs(dx), dy))


@dataclass
class _Estado:
    visto_em: float
    # Início da condição contínua (None = condição não vale agora).
    desde: float | None = None
    ultima_evidencia: float | None = None
    # Imobilidade: âncora (x, y) do pé quando a contagem começou.
    ancora: tuple[float, float] | None = None
    # Ergonomia: segundos acumulados acima de cada limiar.
    acumulado: dict[int, float] = field(default_factory=dict)
    ultimo_angulo: float | None = None
    ultimo_t: float | None = None


class Persistencia:
    """Há quanto tempo uma condição vale sem interrupção, por chave."""

    def __init__(self, tolerancia_s: float = TOLERANCIA_S) -> None:
        self.tolerancia_s = tolerancia_s
        self._estados: dict[Any, _Estado] = {}

    def estado(self, chave, agora: float) -> _Estado:
        est = self._estados.get(chave)
        if est is None:
            est = self._estados[chave] = _Estado(visto_em=agora)
        est.visto_em = agora
        return est

    def atualizar(self, chave, condicao: bool | None, agora: float) -> float:
        """Segundos contínuos com a condição verdadeira (0 se não vale)."""
        est = self.estado(chave, agora)
        if condicao is True:
            if est.desde is None:
                est.desde = agora
            est.ultima_evidencia = agora
        elif condicao is False:
            est.desde = None
        elif est.desde is not None and est.ultima_evidencia is not None and agora - est.ultima_evidencia > self.tolerancia_s:
            est.desde = None  # sem evidência por tempo demais
        return 0.0 if est.desde is None else agora - est.desde

    def esquecer_antigos(self, agora: float) -> None:
        for chave in [c for c, e in self._estados.items() if agora - e.visto_em > ESQUECER_APOS_S]:
            del self._estados[chave]

    def __len__(self) -> int:
        return len(self._estados)


@dataclass(frozen=True)
class ConfigSinais:
    sos_segundos: float = 3.0
    imovel_segundos: float = 20.0
    # Deslocamento máximo do pé, em fração da altura da caixa da pessoa.
    imovel_limiar: float = 0.08
    ergonomia_graus: float = 45.0
    ergonomia_segundos: float = 10.0
    limiares_acumulados: tuple[int, ...] = (45, 60)


class SinaisPorId:
    """Mantém os três sinais por ID e devolve os alertas que valem agora.

    `alertas()` devolve dicionários no formato de `RuleAlert` (rule, severity,
    message, feature, metadata); quem chama os converte. Assim este módulo não
    depende do motor de regras.
    """

    def __init__(self, config: ConfigSinais | None = None) -> None:
        self.config = config or ConfigSinais()
        self.sos = Persistencia()
        self.imovel = Persistencia()
        self.ergonomia = Persistencia()

    def atualizar(
        self,
        poses: list[PoseResult],
        people: list[dict[str, Any]],
        frame_shape,
        agora: float,
        ligados: set[str],
    ) -> list[dict[str, Any]]:
        alertas: list[dict[str, Any]] = []
        rotulos = {p["id"]: p["label"] for p in people}
        cfg = self.config

        for pose in poses:
            if not pose or not pose.found or not pose.person_id:
                continue
            pid = pose.person_id
            rotulo = rotulos.get(pid) or (f"Pessoa {pose.track_id}" if pose.track_id is not None else "Pessoa")
            sujeito = {"person_id": pid, "person_label": rotulo}

            if "sos" in ligados:
                segundos = self.sos.atualizar(pid, bracos_erguidos(pose, frame_shape), agora)
                if segundos >= cfg.sos_segundos:
                    alertas.append(
                        {
                            "rule": "sos_gesto",
                            "severity": "critical",
                            "message": f"SOS: braços erguidos · {rotulo}",
                            "feature": "sos",
                            "metadata": {**sujeito, "method": "punhos_acima_da_cabeca", "segundos": round(segundos, 1)},
                        }
                    )

            if "ergonomia" in ligados:
                angulo = flexao_do_tronco(pose, frame_shape)
                est = self.ergonomia.estado(pid, agora)
                if angulo is not None and est.ultimo_angulo is not None and est.ultimo_t is not None:
                    dt = min(agora - est.ultimo_t, TOLERANCIA_S)  # não credita buraco longo
                    for limiar in cfg.limiares_acumulados:
                        if angulo >= limiar and est.ultimo_angulo >= limiar:
                            est.acumulado[limiar] = est.acumulado.get(limiar, 0.0) + dt
                if angulo is not None:
                    est.ultimo_angulo, est.ultimo_t = angulo, agora
                cond = None if angulo is None else angulo >= cfg.ergonomia_graus
                segundos = self.ergonomia.atualizar(pid, cond, agora)
                if segundos >= cfg.ergonomia_segundos:
                    alertas.append(
                        {
                            "rule": "ergonomia_tronco",
                            "severity": "medium",
                            "message": f"Postura de risco ergonômico (estimativa) · {rotulo}",
                            "feature": "ergonomia",
                            "metadata": {
                                **sujeito,
                                "method": "flexao_tronco_2d",
                                "angulo_graus": round(angulo, 1) if angulo is not None else None,
                                "segundos": round(segundos, 1),
                                "acumulado_s": {str(k): round(v, 1) for k, v in sorted(est.acumulado.items())},
                                "aviso": "Estimativa por pose 2D. Não é avaliação RULA, REBA nem da NR-17.",
                            },
                        }
                    )

        if "imobilidade" in ligados:
            for pessoa in people:
                pid = pessoa.get("id")
                if pid is None or pessoa.get("track_id") is None:
                    continue
                segundos = self._atualizar_imovel(pid, pessoa, agora)
                if segundos >= cfg.imovel_segundos:
                    alertas.append(
                        {
                            "rule": "pessoa_imovel",
                            "severity": "high",
                            "message": f"Pessoa imóvel na área de risco · {pessoa['label']} (não é diagnóstico)",
                            "feature": "imobilidade",
                            "metadata": {
                                "person_id": pid,
                                "person_label": pessoa["label"],
                                "person_box": pessoa.get("box"),
                                "method": "deslocamento_do_pe",
                                "segundos": round(segundos, 1),
                                "aviso": "Sinal de vídeo para verificação humana; não é diagnóstico.",
                            },
                        }
                    )

        for p in (self.sos, self.imovel, self.ergonomia):
            p.esquecer_antigos(agora)
        return alertas

    def _atualizar_imovel(self, pid, pessoa: dict[str, Any], agora: float) -> float:
        dentro = (pessoa.get("risk_area") or {}).get("status") == "inside"
        caixa = pessoa.get("box") or {}
        est = self.imovel.estado(pid, agora)
        if not dentro or not caixa:
            est.ancora = None
            return self.imovel.atualizar(pid, False, agora)
        x1, y1, x2, y2 = (float(caixa.get(k, 0.0)) for k in ("x1", "y1", "x2", "y2"))
        pe = ((x1 + x2) / 2, y2)
        altura = max(1.0, y2 - y1)
        if est.ancora is not None and math.dist(pe, est.ancora) > self.config.imovel_limiar * altura:
            est.ancora = None
            self.imovel.atualizar(pid, False, agora)  # mexeu: recomeça daqui
        if est.ancora is None:
            est.ancora = pe
        return self.imovel.atualizar(pid, True, agora)
