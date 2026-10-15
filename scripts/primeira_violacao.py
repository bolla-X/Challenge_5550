"""Gabarito da latência de alerta: o primeiro quadro de cada fixture com a violação.

    python scripts/primeira_violacao.py                  # multidao, missing_helmet
    python scripts/primeira_violacao.py --fixture bench --regra missing_helmet

A latência de alerta do `scripts/bench.py` é medida "do primeiro quadro com a
violação na fixture até o evento chegar ao navegador". Este script acha esse
quadro com a REFERÊNCIA (PyTorch@640, os mesmos pesos e limiares da aplicação)
e o `RuleEngine` da própria aplicação, quadro a quadro, sem histerese: é o
primeiro instante em que a violação está na cena E é visível para o modelo de
referência. O que vier depois disso (fila, histerese de confirmação, emissão,
rede) é latência do sistema.

Saída: `bench/primeira_violacao.json` (versionado), lido pelo bench.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from app.services.feature_manager import FeatureManager  # noqa: E402
from app.services.risk_rules import RuleEngine  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402

DESTINO = RAIZ / "bench" / "primeira_violacao.json"
FEATURES = "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,ear_protection"


def reduzir(frame):
    """Mesma redução do worker para câmera cadastrada em 960x540."""
    altura, largura = frame.shape[:2]
    if max(largura, altura) > 1008:
        escala = 960 / max(largura, altura)
        frame = cv2.resize(frame, (round(largura * escala), round(altura * escala)), interpolation=cv2.INTER_AREA)
    return frame


def main() -> int:
    import fetch_fixtures

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture", default="multidao")
    ap.add_argument("--regra", default="missing_helmet")
    ap.add_argument("--max-quadros", type=int, default=300)
    args = ap.parse_args()

    epi = YoloPPEDetector(str(RAIZ / "models" / "vyra_ppe.pt"), confidence=0.35, classes=[0, 1, 2, 3, 5, 11, 12, 13], imgsz=640)
    pessoa = YoloPPEDetector(str(RAIZ / "models" / "yolov8n.pt"), confidence=0.35, classes=[0], imgsz=640)
    motor = RuleEngine(FeatureManager.from_config({"DEFAULT_FEATURES": FEATURES}), cooldown_seconds=0, risk_polygon=[])

    cap = cv2.VideoCapture(str(fetch_fixtures.caminho_da_fixture(args.fixture)))
    achado = None
    i = 0
    while i < args.max_quadros:
        ok, frame = cap.read()
        if not ok:
            break
        frame = reduzir(frame)
        deteccoes = pessoa.detect(frame) + [d for d in epi.detect(frame) if d.label != "person"]
        regras = sorted({a.rule for a in motor.evaluate(deteccoes, None, frame.shape)})
        print(f"  quadro {i}: {len(deteccoes)} deteccoes, regras={regras}")
        if args.regra in regras:
            achado = i
            break
        i += 1
    cap.release()
    if achado is None:
        print(f"[primeira_violacao] {args.regra} nao aparece nos primeiros {i} quadros de {args.fixture}")
        return 1

    dados = json.loads(DESTINO.read_text(encoding="utf-8")) if DESTINO.exists() else {}
    dados.setdefault(args.fixture, {})[args.regra] = {
        "quadro": achado,
        "referencia": "pytorch@640, conf 0,35, RuleEngine sem histerese",
        "features": FEATURES,
    }
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[primeira_violacao] {args.fixture}/{args.regra}: quadro {achado} -> {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
