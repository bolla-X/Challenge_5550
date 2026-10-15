"""Modo privacidade (LGPD): desfoque de rosto em TUDO que sai do worker.

O que sai — o quadro do stream, a miniatura, o snapshot do alerta, o clipe de
replay e a imagem enviada à segunda opinião do LLM — passa por aqui quando o
modo está ligado (padrão). A INFERÊNCIA continua sobre o quadro original: o
modelo precisa ver o capacete, e o desfoque é sobre o que pessoas veem.

Onde desfocar, em ordem de preferência por pessoa:

1. caixa em volta dos keypoints de cabeça (nariz, olhos, orelhas) da pose;
2. sem pose, o TERÇO SUPERIOR da caixa da pessoa (cabeça e ombros).

A margem cresce com a idade da análise: com inferência assíncrona, a caixa é
da última análise, e uma pessoa andando já saiu um pouco dali. Limitação
declarada (não escondida): quem o detector de pessoa NÃO viu não é desfocado.
Nada aqui reconhece ninguém — não há identidade, só posição.

Pixelização em vez de só blur gaussiano: reduzir para poucos blocos e
ampliar de volta descarta a informação (não dá para "desfazer" com nitidez),
e custa menos que um gaussiano de kernel grande.
"""

from __future__ import annotations

import cv2
import numpy as np

CABECA = ("nose", "left_eye", "right_eye", "left_ear", "right_ear")
NOMES_COCO_CABECA = {0, 1, 2, 3, 4}


def regioes_de_rosto(analysis, frame_shape, *, idade_s: float = 0.0) -> list[tuple[int, int, int, int]]:
    altura, largura = frame_shape[:2]
    margem = 0.25 + min(0.6, 0.5 * max(0.0, idade_s))
    regioes = []
    for det in getattr(analysis, "detections", []) or []:
        if not (det.label == "person" or det.category == "person"):
            continue
        caixa = None
        if det.keypoints:
            pontos = [(x, y) for i, (x, y, c) in enumerate(det.keypoints) if i in NOMES_COCO_CABECA and c > 0.3 and (x or y)]
            if len(pontos) >= 2:
                xs, ys = [p[0] for p in pontos], [p[1] for p in pontos]
                lado = max(max(xs) - min(xs), max(ys) - min(ys), (det.box.x2 - det.box.x1) * 0.35)
                cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
                caixa = (cx - lado / 2, cy - lado / 2, cx + lado / 2, cy + lado / 2)
        if caixa is None:
            terco = (det.box.y2 - det.box.y1) / 3
            caixa = (det.box.x1, det.box.y1, det.box.x2, det.box.y1 + terco)
        x1, y1, x2, y2 = caixa
        mx, my = (x2 - x1) * margem, (y2 - y1) * margem
        regioes.append((
            max(0, int(x1 - mx)), max(0, int(y1 - my)),
            min(largura, int(x2 + mx)), min(altura, int(y2 + my)),
        ))
    return [r for r in regioes if r[2] > r[0] and r[3] > r[1]]


# Olhos e nariz (COCO 0, 1, 2): o rosto sem o alto da cabeça, onde fica o capacete.
PONTOS_DO_ROSTO = {0, 1, 2}


def regioes_de_olhos_e_nariz(detections, frame_shape) -> list[tuple[int, int, int, int]] | None:
    """Caixa justa em volta de olhos e nariz de cada pessoa, para o recorte do G9.

    None quando alguma pessoa não tem esses keypoints: aí não dá para garantir o
    desfoque do rosto sem cobrir o capacete, e o recorte não é feito.
    """
    altura, largura = frame_shape[:2]
    regioes = []
    for det in detections or []:
        if not (det.label == "person" or det.category == "person"):
            continue
        pontos = [(x, y) for i, (x, y, c) in enumerate(det.keypoints or ()) if i in PONTOS_DO_ROSTO and c > 0.3 and (x or y)]
        if len(pontos) < 2:
            return None
        xs, ys = [q[0] for q in pontos], [q[1] for q in pontos]
        lado = max(max(xs) - min(xs), max(ys) - min(ys), 8.0)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2 + lado * 0.4
        regioes.append((max(0, int(cx - lado * 1.1)), max(0, int(cy - lado * 0.9)),
                        min(largura, int(cx + lado * 1.1)), min(altura, int(cy + lado * 1.2))))
    return [r for r in regioes if r[2] > r[0] and r[3] > r[1]]


def desfocar(frame: np.ndarray, regioes) -> np.ndarray:
    """Cópia do quadro com as regiões pixelizadas. Sem regiões, devolve o próprio."""
    if not regioes:
        return frame
    saida = frame.copy()
    for x1, y1, x2, y2 in regioes:
        roi = saida[y1:y2, x1:x2]
        h, w = roi.shape[:2]
        if h < 2 or w < 2:
            continue
        pequeno = cv2.resize(roi, (max(1, w // 12), max(1, h // 12)), interpolation=cv2.INTER_AREA)
        saida[y1:y2, x1:x2] = cv2.resize(pequeno, (w, h), interpolation=cv2.INTER_NEAREST)
    return saida
