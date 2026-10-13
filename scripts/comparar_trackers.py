"""Tracker IoU (atual) x ByteTrack, nas fixtures — métrica de fragmentação.

    python scripts/comparar_trackers.py

Mesmas detecções para os dois (o detector de pessoa da aplicação), na taxa em
que a inferência realmente roda (um frame a cada `--passo` da fixture, ~5 Hz
para vídeo de 25–30 fps). O IoU recebe só as caixas ≥ 0,35 (como hoje); o
ByteTrack recebe a partir de 0,1, que é como ele é usado.

Pessoas REAIS por fixture foram contadas a olho em folhas de contato dos
quadros (docs/NEXT2026/CHANGELOG.md): bench = 3; queda = 9 (7 na cena da
escada + 2 depois do corte de cena — identidade não atravessa corte). A
multidão tem mais de 30 pessoas e não foi contada com confiança: lá só os IDs
são reportados, sem afirmar fragmentação.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from app.vision.person_tracker import ByteTrackPessoas, PersonTracker  # noqa: E402
from app.vision.yolo_pose_detector import YoloPoseDetector  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402

PESSOAS_REAIS = {"bench": 3, "queda": 9, "multidao": None}


def p95(valores):
    valores = sorted(valores)
    return round(valores[max(0, int(len(valores) * 0.95) - 1)], 3) if valores else None


def main() -> int:
    import fetch_fixtures

    ap = argparse.ArgumentParser()
    ap.add_argument("--passo", type=int, default=6)
    ap.add_argument("--detector", choices=["pose", "yolov8n"], default="pose")
    ap.add_argument("--imgsz", type=int, default=416)
    args = ap.parse_args()

    if args.detector == "pose":
        det = YoloPoseDetector(str(RAIZ / "models" / "yolo11n-pose.pt"), confidence=0.1, imgsz=args.imgsz)
    else:
        det = YoloPPEDetector(str(RAIZ / "models" / "yolov8n.pt"), confidence=0.1, imgsz=args.imgsz, classes=[0])

    resultados = {}
    for nome in ("bench", "queda", "multidao"):
        cap = cv2.VideoCapture(str(fetch_fixtures.caminho_da_fixture(nome)))
        iou, bt = PersonTracker(), ByteTrackPessoas(limiar_ativacao=0.35)
        ids_iou, ids_bt, ms_iou, ms_bt, i, quadros = set(), set(), [], [], 0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % args.passo == 0:
                quadros += 1
                todas = det.detect(frame)
                fortes = [d for d in todas if d.confidence >= 0.35]
                t = time.perf_counter()
                ids_iou |= {d.track_id for d in iou.update(fortes)}
                ms_iou.append((time.perf_counter() - t) * 1000)
                t = time.perf_counter()
                ids_bt |= {d.track_id for d in bt.update(todas)}
                ms_bt.append((time.perf_counter() - t) * 1000)
            i += 1
        reais = PESSOAS_REAIS[nome]
        resultados[nome] = {
            "quadros_inferidos": quadros,
            "pessoas_reais": reais,
            "iou": {"ids_unicos": len(ids_iou), "fragmentacoes": (len(ids_iou) - reais) if reais else None,
                    "ms_p95": p95(ms_iou)},
            "bytetrack": {"ids_unicos": len(ids_bt), "fragmentacoes": (len(ids_bt) - reais) if reais else None,
                          "ms_p95": p95(ms_bt)},
        }
        print(nome, json.dumps(resultados[nome], ensure_ascii=False))

    destino = RAIZ / "bench" / "results" / f"trackers-{args.detector}-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps({"passo": args.passo, "detector": args.detector, "imgsz": args.imgsz,
                                   "resultados": resultados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(destino.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
