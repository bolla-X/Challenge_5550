"""Tracker IoU (atual) x ByteTrack, nas fixtures — métrica de fragmentação.

    python scripts/comparar_trackers.py                       # yolov8n@640, ~5 Hz
    python scripts/comparar_trackers.py --passo 50            # ~0,5 Hz (taxa medida no perfil batata)

Perfil batata: rode com VISIONEPI_CPUS=<2 núcleos> VISIONEPI_THREADS=2
OMP_NUM_THREADS=2 no ambiente (o mesmo do scripts/bench.py). O custo do
tracker sai junto com o p95 da inferência do detector NA MESMA rodada, e a
razão entre os dois é o critério do portão (ByteTrack ≤ 3 % da inferência).

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

import os

# Afinidade ANTES dos imports pesados, como no run.py.
if os.getenv("VISIONEPI_CPUS", "").strip():
    import psutil

    psutil.Process().cpu_affinity([int(c) for c in os.environ["VISIONEPI_CPUS"].split(",") if c.strip().isdigit()])

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from app.utils.limites_de_cpu import aplicar_limites_de_cpu  # noqa: E402
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
    ap.add_argument("--detector", choices=["pose", "yolov8n"], default="yolov8n")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()
    limites = aplicar_limites_de_cpu()

    if args.detector == "pose":
        det = YoloPoseDetector(str(RAIZ / "models" / "yolo11n-pose.pt"), confidence=0.1, imgsz=args.imgsz)
    else:
        det = YoloPPEDetector(str(RAIZ / "models" / "yolov8n.pt"), confidence=0.1, imgsz=args.imgsz, classes=[0])

    resultados = {}
    for nome in ("bench", "queda", "multidao"):
        cap = cv2.VideoCapture(str(fetch_fixtures.caminho_da_fixture(nome)))
        iou, bt = PersonTracker(), ByteTrackPessoas(limiar_ativacao=0.35)
        ids_iou, ids_bt, ms_iou, ms_bt, ms_det, i, quadros = set(), set(), [], [], [], 0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % args.passo == 0:
                quadros += 1
                t = time.perf_counter()
                todas = det.detect(frame)
                ms_det.append((time.perf_counter() - t) * 1000)
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
            "inferencia_ms_p95": p95(ms_det[1:]),  # sem o 1º (aquecimento do modelo)
            "pessoas_reais": reais,
            "iou": {"ids_unicos": len(ids_iou), "fragmentacoes": (len(ids_iou) - reais) if reais else None,
                    "ms_p95": p95(ms_iou)},
            "bytetrack": {"ids_unicos": len(ids_bt), "fragmentacoes": (len(ids_bt) - reais) if reais else None,
                          "ms_p95": p95(ms_bt)},
        }
        inf = resultados[nome]["inferencia_ms_p95"]
        resultados[nome]["bytetrack"]["fracao_da_inferencia_p95"] = round(p95(ms_bt) / inf, 4) if inf else None
        print(nome, json.dumps(resultados[nome], ensure_ascii=False))

    destino = RAIZ / "bench" / "results" / f"trackers-{args.detector}-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps({"passo": args.passo, "detector": args.detector, "imgsz": args.imgsz, "limites_de_cpu": limites,
                                   "resultados": resultados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(destino.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
