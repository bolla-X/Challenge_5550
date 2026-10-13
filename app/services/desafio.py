"""“Você vs. a IA” (G2): o mesmo quadro para a pessoa e para o modelo, um gabarito.

Gabarito curado À MÃO a partir de quadros das gravações de demonstração
(docs/NEXT2026/GABARITO.md): cada pessoa inteira no quadro, com caixa
aproximada em 960×540, marcada como "sem capacete" ou não. Pessoa cortada pela
borda é NEUTRA: clicar nela não conta acerto nem erro (nem para a IA).

Regras da comparação, iguais para os dois lados:
- acerto = um clique (ou uma caixa da IA) dentro de uma pessoa do gabarito
  marcada "sem capacete", contada uma vez;
- erro = clique (ou caixa da IA) em pessoa marcada "com capacete" ou fora de
  qualquer pessoa (exceto as neutras);
- perdido = pessoa "sem capacete" que ninguém apontou.
A IA aponta uma pessoa quando o EPI "capacete" dela sai "missing" no mesmo
casamento EPI↔pessoa que gera os alertas (PersonComplianceMatcher). Se a IA
errar, o placar mostra — é o ponto do exercício.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import cv2
import numpy as np

from app.vision.person_compliance_matcher import PersonComplianceMatcher
from app.vision.privacidade import desfocar

LARGURA, ALTURA = 960, 540
QUADROS_DO_CLIPE = 16  # ~1,6 s antes do quadro da pergunta, a 10 quadros/s
PASSO_DO_CLIPE = 3     # a cada 3 quadros da fonte (30 fps → 10 fps)

# (x1, y1, x2, y2) em 960×540; "sem_capacete": True/False/None (None = neutra).
RODADAS: list[dict[str, Any]] = [
    {
        "id": "canteiro-94", "fixture": "bench", "quadro": 94,
        "pergunta": "Clique em quem está SEM capacete.",
        "pessoas": [
            {"caixa": (205, 120, 315, 375), "sem_capacete": False},
            {"caixa": (362, 258, 458, 408), "sem_capacete": False},
            {"caixa": (318, 300, 372, 432), "sem_capacete": False},
            {"caixa": (878, 300, 948, 425), "sem_capacete": False},
        ],
    },
    {
        "id": "multidao-168", "fixture": "multidao", "quadro": 168,
        "pergunta": "Área de obra: capacete obrigatório. Clique em quem está SEM capacete.",
        "pessoas": [
            {"caixa": (0, 115, 82, 448), "sem_capacete": True},
            {"caixa": (232, 72, 372, 508), "sem_capacete": True},
            {"caixa": (378, 96, 502, 488), "sem_capacete": True},
            {"caixa": (562, 64, 768, 492), "sem_capacete": True},
            {"caixa": (766, 136, 842, 412), "sem_capacete": True},
            {"caixa": (815, 0, 960, 540), "sem_capacete": None},
        ],
    },
    {
        "id": "canteiro-157", "fixture": "bench", "quadro": 157,
        "pergunta": "Clique em quem está SEM capacete.",
        "pessoas": [
            {"caixa": (95, 55, 195, 285), "sem_capacete": False},
            {"caixa": (345, 260, 452, 395), "sem_capacete": False},
            {"caixa": (432, 293, 495, 415), "sem_capacete": False},
        ],
    },
]


def _dentro(ponto, caixa) -> bool:
    x, y = ponto
    x1, y1, x2, y2 = caixa
    return x1 <= x <= x2 and y1 <= y <= y2


def pontuar(pessoas: list[dict[str, Any]], pontos: list[tuple[float, float]]) -> dict[str, Any]:
    """Acertos, erros e perdidos de uma lista de pontos (cliques ou centros das caixas da IA)."""
    alvos = [i for i, p in enumerate(pessoas) if p["sem_capacete"]]
    apontados: set[int] = set()
    erros = 0
    for ponto in pontos:
        # Pessoa mais "interna" que contém o ponto (caixas se sobrepõem).
        candidatas = [i for i, p in enumerate(pessoas) if _dentro(ponto, p["caixa"])]
        if not candidatas:
            erros += 1
            continue
        def area(k: int) -> float:
            x1, y1, x2, y2 = pessoas[k]["caixa"]
            return (x2 - x1) * (y2 - y1)

        i = min(candidatas, key=area)
        if pessoas[i]["sem_capacete"] is None:
            continue  # neutra
        if pessoas[i]["sem_capacete"]:
            if i in apontados:
                continue  # dois cliques na mesma pessoa contam uma vez
            apontados.add(i)
        else:
            erros += 1
    return {"acertos": len(apontados), "erros": erros, "perdidos": len(set(alvos) - apontados), "alvos": len(alvos)}


class Desafio:
    """Quadros (desfocados) e a resposta da IA, preparados uma vez por rodada."""

    def __init__(self, caminhos_das_fixtures: dict[str, str], detector=None, person_detector=None, lock=None) -> None:
        self.caminhos = caminhos_das_fixtures
        self.detector = detector
        self.person_detector = person_detector
        self.lock = lock or threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    @staticmethod
    def rodada(ident: str) -> dict[str, Any]:
        for r in RODADAS:
            if r["id"] == ident:
                return r
        raise LookupError("rodada não existe")

    def publicas(self) -> list[dict[str, Any]]:
        return [{"id": r["id"], "pergunta": r["pergunta"], "quadros": QUADROS_DO_CLIPE} for r in RODADAS]

    def _preparar(self, ident: str) -> dict[str, Any]:
        with self._cache_lock:
            if ident in self._cache:
                return self._cache[ident]
        r = self.rodada(ident)
        cap = cv2.VideoCapture(self.caminhos[r["fixture"]])
        quadros = []
        try:
            for k in range(QUADROS_DO_CLIPE):
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, r["quadro"] - (QUADROS_DO_CLIPE - 1 - k) * PASSO_DO_CLIPE))
                ok, img = cap.read()
                if not ok:
                    raise LookupError("fixture indisponível")
                quadros.append(cv2.resize(img, (LARGURA, ALTURA), interpolation=cv2.INTER_AREA))
        finally:
            cap.release()
        ia = self._resposta_da_ia(quadros[-1])
        # Desfoque (F4) da cabeça de toda pessoa conhecida: gabarito + IA.
        caixas = [p["caixa"] for p in r["pessoas"]] + [tuple(c) for c in ia["caixas_pessoas"]]
        regioes = []
        for x1, y1, x2, y2 in caixas:
            terco = (y2 - y1) / 3
            mx, my = (x2 - x1) * 0.15, terco * 0.25
            regioes.append((max(0, int(x1 - mx)), max(0, int(y1 - my)), min(LARGURA, int(x2 + mx)), min(ALTURA, int(y1 + terco + my))))
        jpegs = [cv2.imencode(".jpg", desfocar(q, regioes), [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes() for q in quadros]
        preparado = {"jpegs": jpegs, "ia": ia}
        with self._cache_lock:
            self._cache[ident] = preparado
        return preparado

    def _resposta_da_ia(self, quadro: np.ndarray) -> dict[str, Any]:
        if self.detector is None:
            return {"pontos": [], "caixas": [], "caixas_pessoas": [], "tempo_ms": None}
        inicio = time.perf_counter()
        with self.lock:
            epis = self.detector.detect(quadro)
            pessoas = self.person_detector.detect(quadro) if self.person_detector is not None else []
        tempo_ms = (time.perf_counter() - inicio) * 1000
        pessoas = [d for d in pessoas if d.label == "person" or d.category == "person"] or [
            d for d in epis if d.label == "person" or d.category == "person"]
        outras = [d for d in epis if not (d.label == "person" or d.category == "person")]
        chaves = {"helmet": True}
        estado = PersonComplianceMatcher().build(outras + pessoas, supported_ppe=chaves, enabled_ppe=chaves,
                                                 frame_shape=quadro.shape)
        apontadas = [p["box"] for p in estado if p["ppe"]["helmet"]["status"] == "missing"]
        return {
            "pontos": [((b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2) for b in apontadas],
            "caixas": [[b["x1"], b["y1"], b["x2"], b["y2"]] for b in apontadas],
            "caixas_pessoas": [[d.box.x1, d.box.y1, d.box.x2, d.box.y2] for d in pessoas],
            "tempo_ms": round(tempo_ms, 1),
        }

    def quadro(self, ident: str, k: int) -> bytes:
        jpegs = self._preparar(ident)["jpegs"]
        if not 0 <= k < len(jpegs):
            raise LookupError("quadro fora do clipe")
        return jpegs[k]

    def responder(self, ident: str, cliques: list[tuple[float, float]], tempo_ms: float | None) -> dict[str, Any]:
        r = self.rodada(ident)
        ia = self._preparar(ident)["ia"]
        return {
            "gabarito": [{"caixa": list(p["caixa"]), "sem_capacete": p["sem_capacete"]} for p in r["pessoas"]],
            "humano": pontuar(r["pessoas"], cliques) | {"tempo_ms": tempo_ms},
            "ia": pontuar(r["pessoas"], ia["pontos"]) | {"tempo_ms": ia["tempo_ms"], "caixas": ia["caixas"]},
        }

