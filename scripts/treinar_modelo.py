"""Treina o detector VisionEPI no Construction-PPE — os argumentos EXATOS da Sprint 4.

Por que treinar, e nao so trocar de peso pronto: o Vyra (Sprints 2 e 3) detecta
capacete com confianca 0,14 a 0,26 em capacete visivel a olho nu (BENCH.md,
Fase 9) e a classe Person dele nao generaliza (README). O resultado e alerta
falso de "sem capacete" em quem esta de capacete. Medido por pessoa no
conjunto de teste, ver docs/SPRINT4.md.

Escolhas, e o motivo de cada uma:

- ``yolov8n.pt`` (COCO) como ponto de partida: ja sabe o que e pessoa, e o
  ``n`` custa uma fracao do ``m`` do Vyra em CPU.
- ``imgsz=416``: e a resolucao em que o pipeline RODA (YOLO_IMGSZ=416). Treinar
  a 640 e inferir a 416 foi exatamente o descasamento do Vyra.
- ``seed=0`` + ``deterministic=True``: o numero tem que poder ser refeito.
- ``val`` so para escolha de checkpoint e de politica; o ``test`` nao e tocado
  antes da avaliacao final.

Medido nesta execucao (CPU Intel Xeon 2,1 GHz, 2 nucleos, sem GPU): ~3,8 min
por epoca.

    python scripts/baixar_dataset.py
    python scripts/treinar_modelo.py            # ~2,6 h em CPU de 2 nucleos
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARGS = {
    "model": "models/yolov8n.pt",
    "data": "datasets/cppe.yaml",
    "epochs": 40,
    "imgsz": 416,
    "batch": 16,
    "workers": 2,
    "device": "cpu",
    "patience": 12,
    "seed": 0,
    "deterministic": True,
    "amp": False,
    "project": "runs_treino",
    "name": "cppe_n416",
    "exist_ok": True,
}
DESTINO = RAIZ / "models" / "visionepi_cppe_n416.pt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=ARGS["epochs"])
    args = parser.parse_args()
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics nao instalado: pip install -r requirements.txt", file=sys.stderr)
        return 1
    cfg = dict(ARGS, epochs=args.epochs)
    modelo = YOLO(str(RAIZ / cfg.pop("model")))
    resultado = modelo.train(**cfg)
    melhor = Path(resultado.save_dir) / "weights" / "best.pt"
    shutil.copy2(melhor, DESTINO)
    print(f"peso final: {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
