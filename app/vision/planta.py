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
            **estado_de_conformidade(pessoa),
        })
    return saida


def estado_de_conformidade(pessoa: dict[str, Any]) -> dict[str, Any]:
    """Cor do avatar no gêmeo digital (X1): sem EPI exigido > na zona > conforme.

    "Não verificável" (fora do enquadramento) NÃO conta como faltando: não
    detectado não é ausente.
    """
    faltando = sorted(
        chave for chave, item in (pessoa.get("ppe") or {}).items() if (item or {}).get("status") in ("missing", "incorrect")
    )
    na_zona = (pessoa.get("risk_area") or {}).get("status") == "inside"
    caida = bool((pessoa.get("pose") or {}).get("fallen"))
    estado = "emergencia" if caida else "sem_epi" if faltando else "zona" if na_zona else "conforme"
    return {"estado": estado, "faltando": faltando}


def recortar(poligono: list[Ponto], recorte: list[Ponto]) -> list[Ponto]:
    """Sutherland–Hodgman: a parte de `poligono` dentro do quadrilátero CONVEXO `recorte`."""
    if len(poligono) < 3 or len(recorte) < 3:
        return []
    area = sum(recorte[i][0] * recorte[(i + 1) % len(recorte)][1] - recorte[(i + 1) % len(recorte)][0] * recorte[i][1]
               for i in range(len(recorte)))
    sentido = 1.0 if area > 0 else -1.0

    def dentro_da_aresta(p: Ponto, a: Ponto, b: Ponto) -> bool:
        return sentido * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) >= 0

    def cruzamento(p: Ponto, q: Ponto, a: Ponto, b: Ponto) -> Ponto:
        x1, y1, x2, y2, x3, y3, x4, y4 = *p, *q, *a, *b
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    saida = list(poligono)
    for i in range(len(recorte)):
        a, b = recorte[i], recorte[(i + 1) % len(recorte)]
        entrada, saida = saida, []
        for j, atual in enumerate(entrada):
            anterior = entrada[j - 1]
            if dentro_da_aresta(atual, a, b):
                if not dentro_da_aresta(anterior, a, b):
                    saida.append(cruzamento(anterior, atual, a, b))
                saida.append(atual)
            elif dentro_da_aresta(anterior, a, b):
                saida.append(cruzamento(anterior, atual, a, b))
        if not saida:
            return []
    # Vértice repetido (a zona encosta num canto do recorte) não vira lado de tamanho zero.
    unicos = [p for i, p in enumerate(saida) if abs(p[0] - saida[i - 1][0]) > 1e-9 or abs(p[1] - saida[i - 1][1]) > 1e-9]
    return unicos if len(unicos) >= 3 else []


def poligono_na_planta(poligono: list[Ponto], calibracao: dict[str, Any]) -> list[Ponto]:
    """A zona de risco (desenhada na imagem) levada para a planta.

    Só a parte da zona que cai no chão CALIBRADO: acima do horizonte a
    homografia não vale (o ponto vai para longe, ou para o outro lado), e a
    zona aparecia fora do galpão no gêmeo digital.
    """
    if not poligono:
        return []
    matriz = homografia(calibracao["pontos_camera"], calibracao["pontos_planta"])
    quad = [(float(x), float(y)) for x, y in calibracao["pontos_camera"]]
    no_chao = recortar([(float(p[0]), float(p[1])) for p in poligono], quad)
    if len(no_chao) < 3:
        return []
    return [(round(x, 4), round(y, 4)) for x, y in projetar(matriz, no_chao)]
