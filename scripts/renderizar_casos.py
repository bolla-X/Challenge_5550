"""Desenha casos de acerto e erro a partir de um ``_bruto.json`` da avaliacao.

Para cada imagem pedida, mostra lado a lado o GROUND TRUTH (o que a anotacao
diz de cada pessoa) e a SAIDA do sistema (caixas detectadas e o status de
capacete/colete por pessoa, na politica escolhida). E a evidencia qualitativa
que acompanha as metricas: cada print pode ser conferido contra a anotacao.

    python scripts/renderizar_casos.py docs/avaliacao/cppe_test_416_bruto.json \\
        --imagens image1120.jpg,image122.jpg --politica evidencia --saida docs/evidencias/casos
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

COR = {"ok": (80, 200, 80), "missing": (60, 60, 230), "unverified": (0, 190, 255), "unsupported": (160, 160, 160)}
COR_GT = {"presente": (80, 200, 80), "ausente": (60, 60, 230), "nao_visivel": (170, 170, 170)}
ROTULO = {"helmet": "capacete", "vest": "colete"}
TXT = {"ok": "ok", "missing": "SEM", "unverified": "?", "presente": "com", "ausente": "SEM", "nao_visivel": "n/v"}


def _texto(img, txt, org, cor, escala=0.55):
    x, y = org
    (w, h), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, escala, 1)
    cv2.rectangle(img, (x, y - h - 4), (x + w + 4, y + 2), (20, 20, 20), -1)
    cv2.putText(img, txt, (x + 2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, escala, cor, 1, cv2.LINE_AA)


def _painel(img, pessoas, cores, titulo, deteccoes=None):
    out = img.copy()
    if deteccoes:
        for d in deteccoes:
            if d["label"] == "person":
                continue
            b = d["box"]
            negativa = d["label"].startswith("no_")
            cv2.rectangle(out, (b["x1"], b["y1"]), (b["x2"], b["y2"]), (60, 60, 230) if negativa else (255, 200, 60), 1)
    for i, p in enumerate(pessoas, 1):
        b = p["caixa"]
        cv2.rectangle(out, (b["x1"], b["y1"]), (b["x2"], b["y2"]), (240, 240, 240), 2)
        y = max(18, b["y1"] + 16)
        for epi in ("helmet", "vest"):
            st = p["status"][epi]
            _texto(out, f"P{i} {ROTULO[epi]}: {TXT.get(st, st)}", (b["x1"] + 3, y), cores.get(st, (255, 255, 255)))
            y += 20
    faixa = np.full((34, out.shape[1], 3), 25, np.uint8)
    cv2.putText(faixa, titulo, (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (235, 235, 235), 1, cv2.LINE_AA)
    return np.vstack([faixa, out])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bruto")
    parser.add_argument("--imagens", required=True)
    parser.add_argument("--politica", default="evidencia")
    parser.add_argument("--dataset", default=str(RAIZ / "datasets" / "construction-ppe"))
    parser.add_argument("--saida", default=str(RAIZ / "docs" / "evidencias" / "casos"))
    parser.add_argument("--prefixo", default="")
    parser.add_argument("--largura", type=int, default=640)
    args = parser.parse_args()

    bruto = json.loads(Path(args.bruto).read_text(encoding="utf-8"))
    por_nome = {r["imagem"]: r for r in bruto["por_imagem"]}
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    for nome in args.imagens.split(","):
        r = por_nome[nome]
        img = cv2.imread(str(Path(args.dataset) / "images" / bruto["split"] / nome))
        esq = _painel(img, r["gt"], COR_GT, "anotacao (ground truth)")
        dir_ = _painel(img, r["politicas"][args.politica], COR, f"sistema: {bruto['config']} / {args.politica}", r["deteccoes"])
        lado = np.hstack([esq, np.full((esq.shape[0], 6, 3), 255, np.uint8), dir_])
        escala = (2 * args.largura) / lado.shape[1]
        lado = cv2.resize(lado, (int(lado.shape[1] * escala), int(lado.shape[0] * escala)), interpolation=cv2.INTER_AREA)
        saida = destino / f"{args.prefixo}{Path(nome).stem}_{bruto['config']}_{args.politica}.jpg"
        cv2.imwrite(str(saida), lado, [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(saida.relative_to(RAIZ) if saida.is_relative_to(RAIZ) else saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
