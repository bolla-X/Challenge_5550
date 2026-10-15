"""Grava as detecções de um peso nos quadros do guarda, para comparar versões do ultralytics.

    python scripts/dump_deteccoes.py models/vyra_ppe.pt saida.json
    PYTHONPATH=bench/_ul84 YOLO_CONFIG_DIR=bench/runtime/ul84_config python scripts/dump_deteccoes.py ...

Mesmos quadros e mesmo emparelhamento de `scripts/concordancia.py` (classe +
IoU ≥ 0,5). `--comparar a.json b.json` imprime a concordância por classe de b
contra a. Existe para a checagem do F8 (YOLOE-26 exige ultralytics 8.4: o Vyra
treinado no 8.3 tem de continuar detectando igual).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))


def gravar(peso: str, destino: str) -> None:
    import ultralytics
    from concordancia import amostrar_quadros
    from ultralytics import YOLO

    modelo = YOLO(peso)
    saida = {"ultralytics": ultralytics.__version__, "quadros": []}
    for nome, i, frame in amostrar_quadros(40):
        r = modelo.predict(frame, imgsz=640, conf=0.35, classes=[0, 1, 2, 3, 5, 11, 12, 13], verbose=False)[0]
        caixas = [[int(c), *map(float, b)] for c, b in zip(r.boxes.cls.tolist(), r.boxes.xyxy.tolist(), strict=True)]
        saida["quadros"].append({"fixture": nome, "i": i, "caixas": caixas})
    Path(destino).write_text(json.dumps(saida), encoding="utf-8")
    print(f"{destino}: ultralytics {ultralytics.__version__}, {len(saida['quadros'])} quadros")


def _iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    uniao = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 0.0


def comparar(ref_json: str, cand_json: str) -> None:
    ref, cand = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (ref_json, cand_json))
    por_classe: dict[int, list[int]] = {}
    for qr, qc in zip(ref["quadros"], cand["quadros"], strict=True):
        for c, *_ in qr["caixas"]:
            por_classe.setdefault(c, [0, 0, 0])[1] += 1
        for c, *_ in qc["caixas"]:
            por_classe.setdefault(c, [0, 0, 0])[2] += 1
        pares = sorted(((_iou(a[1:], b[1:]), i, j) for i, a in enumerate(qr["caixas"]) for j, b in enumerate(qc["caixas"])
                        if a[0] == b[0]), reverse=True)
        ur, uc = set(), set()
        for v, i, j in pares:
            if v < 0.5:
                break
            if i in ur or j in uc:
                continue
            ur.add(i)
            uc.add(j)
            por_classe[qr["caixas"][i][0]][0] += 1
    total = [sum(v[k] for v in por_classe.values()) for k in range(3)]
    print(f"referência ultralytics {ref['ultralytics']} × candidato {cand['ultralytics']}")
    for c, (m, nr, nc) in sorted(por_classe.items()):
        print(f"  classe {c}: batidas {m}, ref {nr}, cand {nc}, concordância {2 * m / (nr + nc):.4f}")
    m, nr, nc = total
    print(f"  TOTAL: concordância {2 * m / (nr + nc):.4f} ({m} batidas, {nr} ref, {nc} cand)" if nr + nc else "  sem caixas")


if __name__ == "__main__":
    if sys.argv[1] == "--comparar":
        comparar(sys.argv[2], sys.argv[3])
    else:
        gravar(sys.argv[1], sys.argv[2])
