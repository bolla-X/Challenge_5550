"""Guarda de qualidade sem rótulo manual: concordância com a referência.

    python scripts/concordancia.py                       # todos os candidatos
    python scripts/concordancia.py --candidatos pytorch:416,onnx:416
    python scripts/concordancia.py --modelo pessoa       # o detector de pessoa (yolov8n)

Referência: o MESMO peso em PyTorch, imgsz 640 (a resolução de treino), com os
filtros que a aplicação usa (YOLO_CLASSES, confiança 0,35). Para cada candidato
(runtime × imgsz) e cada quadro amostrado das fixtures, uma detecção do
candidato "bate" com uma da referência se for da MESMA classe e IoU ≥ 0,5
(emparelhamento guloso por IoU, cada detecção usada uma vez).

Duas métricas por classe, porque erram de jeitos diferentes:

- `recall_ref` = batidas / detecções da referência — o que o candidato PERDEU;
- `concordancia` = 2·batidas / (n_ref + n_cand) (Dice) — perdas E invenções.

O guarda da missão usa `concordancia`: ≥ 97 % para troca de runtime e ≥ 95 %
para redução de resolução, no total e reportado por classe (luva e óculos são
pequenos e costumam cair primeiro).

Os tempos medidos aqui são de BANCADA (um predict por vez, processo isolado) e
só servem de pista: a decisão de runtime vem do `scripts/bench.py`, com o
servidor real — a nota de projeto "OpenVINO ganha na bancada e perde no worker"
existe por isso.

Exportações ficam em `models/export/` (fora do git, como os pesos); nada em
`models/` é sobrescrito.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402

DIR_EXPORT = RAIZ / "models" / "export"
DIR_CALIB = RAIZ / "bench" / "runtime" / "calib"
MODELOS = {
    "epi": {"peso": RAIZ / "models" / "vyra_ppe.pt", "classes": [0, 1, 2, 3, 5, 11, 12, 13]},
    "pessoa": {"peso": RAIZ / "models" / "yolov8n.pt", "classes": [0]},
}
FIXTURES = ["bench", "multidao", "queda"]
CANDIDATOS_PADRAO = [
    "pytorch:512", "pytorch:416", "pytorch:320",
    "onnx:640", "onnx:416", "onnx:320",
    "openvino:640", "openvino:416", "openvino:320",
    "openvino-int8:416",
]
CANDIDATOS_PESSOA = ["pytorch:416", "onnx:640", "openvino:640", "pose:640", "pose:416"]


def amostrar_quadros(por_fixture: int) -> list[tuple[str, int, object]]:
    import fetch_fixtures

    quadros = []
    for nome in FIXTURES:
        caminho = fetch_fixtures.caminho_da_fixture(nome)
        cap = cv2.VideoCapture(str(caminho))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        passo = max(1, total // por_fixture)
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % passo == 0:
                # Mesma redução que o worker faz (câmera cadastrada em 960x540).
                altura, largura = frame.shape[:2]
                if max(largura, altura) > 1008:
                    escala = 960 / max(largura, altura)
                    frame = cv2.resize(frame, (round(largura * escala), round(altura * escala)), interpolation=cv2.INTER_AREA)
                quadros.append((nome, i, frame))
            i += 1
        cap.release()
    return quadros


def exportar(modelo: str, formato: str, imgsz: int, *, int8: bool = False, dinamico: bool = False) -> Path:
    """Exporta (uma vez) o peso para `formato` em `imgsz`. Devolve o caminho carregável."""
    from ultralytics import YOLO

    peso = MODELOS[modelo]["peso"]
    sufixo = f"{peso.stem}_{imgsz}" + ("_int8" if int8 else "") + ("_dyn" if dinamico else "")
    pasta = DIR_EXPORT / sufixo
    pasta.mkdir(parents=True, exist_ok=True)
    copia = pasta / f"{sufixo}.pt"
    if not copia.exists():
        shutil.copy2(peso, copia)
    alvo = pasta / (f"{sufixo}.onnx" if formato == "onnx" else f"{sufixo}_openvino_model")
    if alvo.exists():
        return alvo
    # dynamic=True: a forma de entrada fica livre, então o letterbox é o MESMO
    # do PyTorch (retângulo no múltiplo de 32, não quadrado 640x640) e a
    # comparação mede só o runtime, não o pré-processamento.
    argumentos = {"format": formato, "imgsz": imgsz, "dynamic": dinamico, "half": False, "verbose": False}
    if int8:
        # Doc oficial: https://docs.ultralytics.com/modes/export/ (argumentos int8/data) e
        # https://docs.ultralytics.com/integrations/openvino/ (INT8 via NNCF, calibrado com `data`).
        argumentos |= {"int8": True, "data": str(preparar_calibracao(modelo))}
    if formato == "openvino":
        # O exportador do ultralytics 8.3.40 também usa `openvino.runtime`, que o
        # OpenVINO 2026 removeu — mesmo shim que o detector aplica ao carregar.
        YoloPPEDetector._compatibilizar_openvino()
    inicio = time.perf_counter()
    saida = YOLO(str(copia)).export(**argumentos)
    print(f"  export {formato} imgsz={imgsz}{' int8' if int8 else ''}: {time.perf_counter() - inicio:.1f} s -> {saida}")
    return Path(saida)


def preparar_calibracao(modelo: str) -> Path:
    """Dataset mínimo de calibração INT8: quadros das fixtures, sem rótulo.

    O INT8 calibra as faixas de ativação com imagens representativas — as do
    próprio cenário de uso, não COCO. Rótulo não é usado na calibração.
    """
    from ultralytics import YOLO

    imagens = DIR_CALIB / modelo / "images" / "val"
    imagens.mkdir(parents=True, exist_ok=True)
    if not any(imagens.iterdir()):
        for nome, i, frame in amostrar_quadros(100):
            cv2.imwrite(str(imagens / f"{nome}_{i:05d}.jpg"), frame)
    nomes = YOLO(str(MODELOS[modelo]["peso"])).names
    yaml = DIR_CALIB / modelo / "calib.yaml"
    linhas = [f"path: {(DIR_CALIB / modelo).as_posix()}", "train: images/val", "val: images/val", "names:"]
    linhas += [f"  {k}: {json.dumps(str(v))}" for k, v in sorted(nomes.items())]
    yaml.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return yaml


def detector_para(modelo: str, candidato: str) -> YoloPPEDetector:
    runtime, imgsz = candidato.split(":")
    imgsz = int(imgsz)
    if runtime == "pytorch":
        caminho = MODELOS[modelo]["peso"]
    elif runtime == "onnx":
        caminho = exportar(modelo, "onnx", imgsz)
    elif runtime == "openvino":
        caminho = exportar(modelo, "openvino", imgsz)
    elif runtime == "onnx-dyn":
        caminho = exportar(modelo, "onnx", imgsz, dinamico=True)
    elif runtime == "openvino-dyn":
        caminho = exportar(modelo, "openvino", imgsz, dinamico=True)
    elif runtime == "openvino-int8":
        caminho = exportar(modelo, "openvino", imgsz, int8=True)
    elif runtime == "pose":
        # Troca de MODELO (não de runtime): o YOLO-pose como detector de pessoa.
        from app.vision.yolo_pose_detector import YoloPoseDetector

        return YoloPoseDetector(str(RAIZ / "models" / "yolo11n-pose.pt"), confidence=0.35, imgsz=imgsz)
    else:
        raise SystemExit(f"runtime desconhecido: {runtime}")
    return YoloPPEDetector(str(caminho), confidence=0.35, classes=MODELOS[modelo]["classes"], imgsz=imgsz)


def emparelhar(ref, cand) -> dict[str, list[int]]:
    """Por classe: [batidas, n_ref, n_cand]."""
    por_classe: dict[str, list[int]] = {}
    for d in ref:
        por_classe.setdefault(d.label, [0, 0, 0])[1] += 1
    for d in cand:
        por_classe.setdefault(d.label, [0, 0, 0])[2] += 1
    pares = sorted(
        ((r.box.iou(c.box), i, j) for i, r in enumerate(ref) for j, c in enumerate(cand) if r.label == c.label),
        reverse=True,
    )
    usados_r, usados_c = set(), set()
    for iou, i, j in pares:
        if iou < 0.5:
            break
        if i in usados_r or j in usados_c:
            continue
        usados_r.add(i)
        usados_c.add(j)
        por_classe[ref[i].label][0] += 1
    return por_classe


def resumir(contagens: dict[str, list[int]]) -> dict[str, dict[str, float | int]]:
    saida = {}
    total = [0, 0, 0]
    for classe, (m, nr, nc) in sorted(contagens.items()):
        total = [total[0] + m, total[1] + nr, total[2] + nc]
        saida[classe] = {"batidas": m, "n_ref": nr, "n_cand": nc,
                         "recall_ref": round(m / nr, 4) if nr else None,
                         "concordancia": round(2 * m / (nr + nc), 4) if nr + nc else None}
    m, nr, nc = total
    saida["_total"] = {"batidas": m, "n_ref": nr, "n_cand": nc, "recall_ref": round(m / nr, 4) if nr else None,
                       "concordancia": round(2 * m / (nr + nc), 4) if nr + nc else None}
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description="Concordância de runtime/imgsz com a referência PyTorch@640.")
    ap.add_argument("--modelo", choices=sorted(MODELOS), default="epi")
    ap.add_argument("--candidatos", default="")
    ap.add_argument("--quadros-por-fixture", type=int, default=40)
    args = ap.parse_args()

    if not args.candidatos:
        args.candidatos = ",".join(CANDIDATOS_PESSOA if args.modelo == "pessoa" else CANDIDATOS_PADRAO)
    quadros = amostrar_quadros(args.quadros_por_fixture)
    print(f"[concordancia] {len(quadros)} quadros de {', '.join(FIXTURES)}; modelo {args.modelo}")
    referencia = detector_para(args.modelo, "pytorch:640")
    referencia.detect(quadros[0][2])
    ref = [referencia.detect(f) for _, _, f in quadros]

    resultados = {}
    for candidato in [c.strip() for c in args.candidatos.split(",") if c.strip()]:
        try:
            det = detector_para(args.modelo, candidato)
            for _ in range(3):
                det.detect(quadros[0][2])
            tempos, contagens = [], {}
            for (_, _, frame), r in zip(quadros, ref, strict=True):
                inicio = time.perf_counter()
                cand = det.detect(frame)
                tempos.append((time.perf_counter() - inicio) * 1000)
                for classe, (m, nr, nc) in emparelhar(r, cand).items():
                    acumulado = contagens.setdefault(classe, [0, 0, 0])
                    contagens[classe] = [acumulado[0] + m, acumulado[1] + nr, acumulado[2] + nc]
            erro = det.diagnostics().get("error")
            tempos.sort()
            resultados[candidato] = {
                "por_classe": resumir(contagens),
                "bancada_ms_p50": round(tempos[len(tempos) // 2], 1),
                "bancada_ms_p95": round(tempos[int(len(tempos) * 0.95) - 1], 1),
                "erro": erro,
            }
            tot = resultados[candidato]["por_classe"]["_total"]
            print(f"  {candidato:18s} concordancia {tot['concordancia']}  recall {tot['recall_ref']}  "
                  f"bancada p50 {resultados[candidato]['bancada_ms_p50']} ms" + (f"  ERRO {erro}" if erro else ""))
        except Exception as exc:  # noqa: BLE001  (um candidato quebrado não para os outros)
            resultados[candidato] = {"erro": f"{type(exc).__name__}: {exc}"}
            print(f"  {candidato:18s} FALHOU: {type(exc).__name__}: {exc}")

    destino = RAIZ / "bench" / "results" / f"concordancia-{args.modelo}-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"modelo": args.modelo, "quadros": len(quadros), "referencia": "pytorch:640",
                                   "resultados": resultados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[concordancia] {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
