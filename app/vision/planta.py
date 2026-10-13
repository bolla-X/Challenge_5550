"""Planta baixa ao vivo (G5): homografia imagem da câmera → planta.

Calibração: o técnico marca 4 pontos no CHÃO da imagem da câmera e os 4
correspondentes na planta (coordenadas normalizadas 0–1 nos dois lados). Com
eles, `cv2.getPerspectiveTransform` dá a matriz 3×3 que leva qualquer ponto do
chão da imagem para a planta. Projeta-se o PÉ de cada pessoa (meio da base da
caixa): é o ponto que está no plano do chão — o centro da caixa não está.

Limite honesto: homografia vale para um plano. Pé fora do quadrilátero
calibrado é extrapolação e sai marcado (`dentro_da_calibracao: False`).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

Ponto = tuple[float, float]


def validar_pontos(pontos: Any) -> list[Ponto]:
    if not isinstance(pontos, (list, tuple)) or len(pontos) != 4:
        raise ValueError("são exatamente 4 pontos")
    saida = []
    for p in pontos:
        if isinstance(p, dict):
            p = (p.get("x"), p.get("y"))
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("ponto deve ser [x, y]")
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("coordenada não numérica") from exc
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("coordenadas normalizadas entre 0 e 1")
        saida.append((x, y))
    # Quadrilátero degenerado (3 pontos colineares) não tem homografia útil.
    if abs(cv2.contourArea(np.array(saida, dtype=np.float32))) < 1e-4:
        raise ValueError("os 4 pontos não formam uma área (colineares ou repetidos)")
    return saida


def homografia(pontos_camera: list[Ponto], pontos_planta: list[Ponto]) -> np.ndarray:
    origem = np.array(validar_pontos(pontos_camera), dtype=np.float32)
    destino = np.array(validar_pontos(pontos_planta), dtype=np.float32)
    return cv2.getPerspectiveTransform(origem, destino)


def projetar(matriz: np.ndarray, pontos: list[Ponto]) -> list[Ponto]:
    if not pontos:
        return []
    arr = np.array(pontos, dtype=np.float32).reshape(-1, 1, 2)
    return [(float(x), float(y)) for x, y in cv2.perspectiveTransform(arr, matriz).reshape(-1, 2)]


def dentro(ponto: Ponto, quad: list[Ponto]) -> bool:
    return cv2.pointPolygonTest(np.array(quad, dtype=np.float32), ponto, False) >= 0


def pes_na_planta(people: list[dict[str, Any]], frame_shape, calibracao: dict[str, Any]) -> list[dict[str, Any]]:
    """Um ponto por pessoa rastreada, já na planta. Só o ID de rastreio (não identidade)."""
    altura, largura = frame_shape[:2]
    pes, quem = [], []
    for pessoa in people:
        caixa = pessoa.get("box") or {}
        if pessoa.get("track_id") is None or not caixa:
            continue
        pes.append(((caixa["x1"] + caixa["x2"]) / 2 / max(1, largura), caixa["y2"] / max(1, altura)))
        quem.append(pessoa)
    if not pes:
        return []
    matriz = homografia(calibracao["pontos_camera"], calibracao["pontos_planta"])
    saida = []
    for pessoa, pe, (px, py) in zip(quem, pes, projetar(matriz, pes), strict=True):
        saida.append({
            "track_id": pessoa["track_id"],
            "x": round(px, 4),
            "y": round(py, 4),
            "dentro_da_calibracao": dentro(pe, calibracao["pontos_camera"]),
            "na_zona": (pessoa.get("risk_area") or {}).get("status") == "inside",
        })
    return saida


def poligono_na_planta(poligono: list[Ponto], calibracao: dict[str, Any]) -> list[Ponto]:
    """A zona de risco (desenhada na imagem) levada para a planta."""
    if not poligono:
        return []
    matriz = homografia(calibracao["pontos_camera"], calibracao["pontos_planta"])
    return [(round(x, 4), round(y, 4)) for x, y in projetar(matriz, [(float(p[0]), float(p[1])) for p in poligono])]
