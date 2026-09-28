"""Monta um video de demonstracao a partir de imagens ANOTADAS do conjunto de teste.

Por que existe: a fixture de bench (Wikimedia) so tem 0 a 2 pessoas e nunca
mostra uma violacao, e as cenas da Sprint 3 sao 3. Para a evidencia de execucao
da Sprint 4 o app precisa rodar sobre uma FONTE DE ARQUIVO comum
(VIDEO_SOURCE=...) que contenha, de proposito, os tres tipos de caso: pessoa
conforme, pessoa sem capacete e pessoa sem colete — e cujo ground truth e
conhecido, para que cada print possa ser conferido contra a anotacao.

Selecao deterministica: a partir do ground truth por pessoa (mesmo codigo da
avaliacao), escolhe imagens com 1 a 3 pessoas em cada categoria, na ordem do
nome do arquivo. Cada imagem vira ~2,5 s de video, com letterbox (sem esticar:
pessoa deformada muda o que o modelo ve).

    python scripts/montar_video_demo.py --saida tests/fixtures/demo_sprint4.mp4
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

from app.vision.avaliacao import AUSENTE, PRESENTE, ground_truth_por_pessoa, ler_rotulos_yolo  # noqa: E402
from scripts.avaliar_dataset import NOMES_CPPE, _imagem_de  # noqa: E402

LARGURA, ALTURA, FPS = 1280, 720, 12


def _categoria(gt) -> str | None:
    if not 1 <= len(gt) <= 3:
        return None
    capacete = [p.status["helmet"] for p in gt]
    colete = [p.status["vest"] for p in gt]
    if AUSENTE in capacete:
        return "sem_capacete"
    if AUSENTE in colete:
        return "sem_colete"
    if all(s == PRESENTE for s in capacete) and all(s == PRESENTE for s in colete):
        return "conforme"
    return None


def _letterbox(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    escala = min(LARGURA / w, ALTURA / h)
    nova = cv2.resize(img, (int(w * escala), int(h * escala)), interpolation=cv2.INTER_AREA)
    quadro = np.full((ALTURA, LARGURA, 3), 24, dtype=np.uint8)
    y0 = (ALTURA - nova.shape[0]) // 2
    x0 = (LARGURA - nova.shape[1]) // 2
    quadro[y0 : y0 + nova.shape[0], x0 : x0 + nova.shape[1]] = nova
    return quadro


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(RAIZ / "datasets" / "construction-ppe"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--por-categoria", type=int, default=4)
    parser.add_argument("--segundos", type=float, default=2.5)
    parser.add_argument("--saida", default=str(RAIZ / "tests" / "fixtures" / "demo_sprint4.mp4"))
    args = parser.parse_args()

    raiz = Path(args.dataset)
    escolhidas: dict[str, list[Path]] = {"conforme": [], "sem_capacete": [], "sem_colete": []}
    for rotulo in sorted((raiz / "labels" / args.split).glob("*.txt")):
        caminho = _imagem_de(rotulo, raiz / "images" / args.split)
        if caminho is None:
            continue
        img = cv2.imread(str(caminho))
        if img is None or min(img.shape[:2]) < 400:
            continue
        gt = ground_truth_por_pessoa(ler_rotulos_yolo(rotulo, NOMES_CPPE, largura=img.shape[1], altura=img.shape[0]))
        cat = _categoria(gt)
        if cat and len(escolhidas[cat]) < args.por_categoria:
            escolhidas[cat].append(caminho)

    # Intercala as categorias: conforme, violacao, conforme, violacao...
    ordem: list[tuple[str, Path]] = []
    for i in range(args.por_categoria):
        for cat in ("conforme", "sem_capacete", "sem_colete"):
            if i < len(escolhidas[cat]):
                ordem.append((cat, escolhidas[cat][i]))

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(destino), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (LARGURA, ALTURA))
    quadros_por_imagem = int(round(args.segundos * FPS))
    for _cat, caminho in ordem:
        quadro = _letterbox(cv2.imread(str(caminho)))
        for _ in range(quadros_por_imagem):
            escritor.write(quadro)
    escritor.release()

    roteiro = [{"inicio_s": round(i * args.segundos, 1), "categoria": cat, "imagem": p.name} for i, (cat, p) in enumerate(ordem)]
    destino.with_suffix(".json").write_text(json.dumps(roteiro, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{destino}: {len(ordem)} imagens, {len(ordem) * args.segundos:.1f} s")
    for item in roteiro:
        print(f"  {item['inicio_s']:>5.1f}s  {item['categoria']:13s} {item['imagem']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
