"""Confiança da classe Fall-Detected do Vyra quadro a quadro nas gravações (decisão da regra de emergência).

    python scripts/confianca_de_queda.py --fps 4

Roda o detector de EPI da aplicação (mesmo runtime aprovado) nos quadros de
cada gravação, a `--fps` quadros por segundo de vídeo, e guarda a maior
confiança da classe de queda em cada um. Responde: um quadro sozinho com
confiança alta separa a queda real (gravação `queda`) dos falsos positivos
(`multidao`, `bench`)? Saída em bench/results/confianca-queda-*.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("VISIONEPI_DOTENV", "0")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import cv2  # noqa: E402


def main() -> None:
    import fetch_fixtures
    from ultralytics import YOLO

    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--max-s", type=float, default=60.0)
    ap.add_argument("--modelo", default="models/export/vyra_ppe_640_dyn/vyra_ppe_640_dyn.onnx")
    a = ap.parse_args()
    modelo = YOLO(str(RAIZ / a.modelo), task="detect")
    saida = {"modelo": a.modelo, "fps": a.fps, "gravacoes": {}}
    for nome in ("queda", "multidao", "bench"):
        cap = cv2.VideoCapture(str(fetch_fixtures.caminho_da_fixture(nome)))
        fps_video = cap.get(cv2.CAP_PROP_FPS) or 25.0
        passo = max(1, round(fps_video / a.fps))
        confs, i = [], 0
        while True:
            ok, quadro = cap.read()
            if not ok or i / fps_video > a.max_s:
                break
            if i % passo == 0:
                r = modelo.predict(quadro, imgsz=640, conf=0.10, classes=[0], verbose=False)[0]
                confs.append(round(max((float(c) for c in r.boxes.conf.tolist()), default=0.0), 3))
            i += 1
        cap.release()
        saida["gravacoes"][nome] = {"quadros": len(confs), "confiancas": confs,
                                    "acima_de": {str(t): sum(1 for c in confs if c >= t) for t in (0.35, 0.5, 0.6, 0.7, 0.8)},
                                    "maxima": max(confs, default=0.0)}
        print(nome, saida["gravacoes"][nome]["quadros"], saida["gravacoes"][nome]["acima_de"], "max", saida["gravacoes"][nome]["maxima"],
              flush=True)
    destino = RAIZ / "bench" / "results" / f"confianca-queda-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps(saida, indent=1), encoding="utf-8")
    print(destino)


if __name__ == "__main__":
    main()
