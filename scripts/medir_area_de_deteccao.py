"""Medição da área de detecção (MISSÃO 7, item 4) na gravação `next_multidao.mp4`.

    python scripts/medir_area_de_deteccao.py                       # área padrão: terço do meio
    python scripts/medir_area_de_deteccao.py --area 0.33,0,0.67,1  # retângulo x0,y0,x1,y1 (0–1)
    python scripts/medir_area_de_deteccao.py --mapa                # só onde ficam os pés (por terço)

Usa os MESMOS detectores do servidor (MonitorService: EPI, pessoa e pose, runtime do `auto`) e o MESMO
caminho do worker (`CameraWorker._detectar`), com e sem área, nos mesmos quadros. Mede:

- tempo de inferência por análise (as chamadas de modelo de um quadro), p50 e p95, sem o aquecimento — a
  primeira chamada numa forma nova de entrada compila o modelo (OpenVINO) e é contada à parte;
- pessoas que saíram COM a área e têm os pés fora dela (meta: zero);
- pessoas dentro: contagem com a área contra a inferência no quadro inteiro restrita ao mesmo polígono.

Grava o resultado em bench/results/<data>-area-de-deteccao.json. Não sobe servidor nem abre câmera.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)
os.environ.setdefault("VISIONEPI_DOTENV", "0")
os.environ.setdefault("AUTH_REQUIRED", "false")  # sem servidor nem sessão: só os detectores
os.environ.setdefault("SECRET_KEY", os.urandom(32).hex())
os.environ.setdefault("PPE_MODEL_PATH", "models/vyra_ppe.pt")
os.environ.setdefault("YOLO_CLASSES", "0,1,2,3,5,11,12,13")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + (RAIZ / "bench" / "runtime" / "medir-area.db").as_posix())

FIXTURE = RAIZ / "tests" / "fixtures" / "next_multidao.mp4"


class _SocketNulo:
    def emit(self, *args, **kwargs):  # noqa: ARG002
        pass

    def start_background_task(self, *args, **kwargs):  # noqa: ARG002
        return None


def _quadros(passo: int) -> list:
    import cv2

    captura = cv2.VideoCapture(str(FIXTURE))
    quadros, i = [], 0
    while True:
        ok, quadro = captura.read()
        if not ok:
            break
        if i % passo == 0:
            quadros.append(cv2.resize(quadro, (960, 540)) if quadro.shape[:2] != (540, 960) else quadro)
        i += 1
    captura.release()
    return quadros


def _pessoas(bruto) -> list:
    ppe, pessoas, _ = bruto
    return list(pessoas) + [d for d in ppe if d.label == "person" or d.category == "person"]


def _carga_da_cpu() -> int | None:
    """% de CPU da máquina antes de medir (Windows); None se não der para ler."""
    import subprocess

    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).LoadPercentage"],
                               capture_output=True, text=True, timeout=30).stdout
        return int(saida.split()[0])
    except Exception:  # noqa: BLE001
        return None


def _pct(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round((len(ordenados) - 1) * p)))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", default="0.33,0,0.67,1", help="retângulo x0,y0,x1,y1 normalizado")
    parser.add_argument("--passo", type=int, default=5, help="usa 1 de cada N quadros da gravação")
    parser.add_argument("--mapa", action="store_true")
    args = parser.parse_args()

    from app import create_app
    from app.services.camera_worker import CameraWorker
    from app.vision.area_de_deteccao import AreaDeDeteccao, ponto_dos_pes, ponto_no_poligono

    carga = _carga_da_cpu()
    app = create_app()
    monitor = app.extensions["monitor_service"]
    quadros = _quadros(args.passo)
    x0, y0, x1, y1 = (float(v) for v in args.area.split(","))
    poligono = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    with app.app_context():
        worker = CameraWorker(app, _SocketNulo(), monitor.feature_manager, camera_id=None, source="nunca-aberta", fps=12,
                              detector=monitor.detector, person_detector=monitor.person_detector,
                              pose_estimator=monitor.pose_estimator, pose_detector=monitor.pose_detector,
                              inference_lock=threading.Lock())
        worker.pose_a_cada_k = 1  # pose em toda análise: o pior caso, igual com e sem área

        sem, com = AreaDeDeteccao(None), AreaDeDeteccao(poligono)
        if args.mapa:
            tercos = [0, 0, 0]
            for quadro in quadros:
                worker.area_deteccao = sem
                for p in _pessoas(worker._detectar(quadro, lambda _etapa: None)):
                    tercos[min(2, int(ponto_dos_pes(p.box)[0] / 960 * 3))] += 1
            print(f"pés por terço (esquerda, meio, direita), {len(quadros)} quadros: {tercos}")
            return
        # Intercalado quadro a quadro (e alternando quem vai primeiro): com a CPU disputada por outros
        # programas, duas rodadas seguidas mediriam momentos diferentes da máquina, não a área.
        cheio, com_area = [], []
        t_cheio, t_area, aq_cheio, aq_area = [], [], [], []
        vistas: dict[int, set] = {0: set(), 1: set()}
        for i, quadro in enumerate(quadros):
            for k in ((0, 1) if i % 2 == 0 else (1, 0)):
                area = (sem, com)[k]
                worker.area_deteccao = area
                forma = area.recortar(quadro)[0].shape
                inicio = time.perf_counter()
                bruto = worker._detectar(quadro, lambda _etapa: None)
                ms = (time.perf_counter() - inicio) * 1000.0
                if forma in vistas[k]:
                    (t_cheio, t_area)[k].append(ms)
                else:
                    (aq_cheio, aq_area)[k].append(ms)
                    vistas[k].add(forma)
                (cheio, com_area)[k].append(bruto)

    def dentro(p) -> bool:
        px, py = ponto_dos_pes(p.box)
        return ponto_no_poligono(px / 960, py / 540, poligono)

    fora_com_area = sum(1 for b in com_area for p in _pessoas(b) if not dentro(p))
    dentro_com_area = sum(1 for b in com_area for p in _pessoas(b))
    dentro_cheio = sum(1 for b in cheio for p in _pessoas(b) if dentro(p))
    total_cheio = sum(len(_pessoas(b)) for b in cheio)
    por_quadro = [len(_pessoas(a)) - sum(1 for p in _pessoas(c) if dentro(p)) for a, c in zip(com_area, cheio, strict=True)]
    resultado = {
        "fixture": FIXTURE.name,
        "carga_da_cpu_antes_pct": carga,
        "quadros": len(quadros),
        "area": poligono,
        "fracao_do_quadro": round((x1 - x0) * (y1 - y0), 3),
        "runtime": {k: getattr(d, "runtime", None) for k, d in
                    (("epi", monitor.detector), ("pessoa", monitor.person_detector), ("pose", monitor.pose_detector))},
        "inferencia_ms_sem_area": {"p50": round(statistics.median(t_cheio), 1), "p95": round(_pct(t_cheio, 0.95), 1),
                                   "aquecimento": [round(v) for v in aq_cheio]},
        "inferencia_ms_com_area": {"p50": round(statistics.median(t_area), 1), "p95": round(_pct(t_area, 0.95), 1),
                                   "aquecimento": [round(v) for v in aq_area]},
        "pessoas_fora_da_area_com_area": fora_com_area,
        "pessoas_dentro_com_area": dentro_com_area,
        "pessoas_dentro_no_quadro_inteiro_filtrado": dentro_cheio,
        "pessoas_no_quadro_inteiro": total_cheio,
        "diferenca_dentro": dentro_com_area - dentro_cheio,
        "quadros_com_diferenca": sum(1 for d in por_quadro if d),
        "diferenca_por_quadro_min_max": [min(por_quadro), max(por_quadro)],
    }
    destino = RAIZ / "bench" / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-area-de-deteccao.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    print(f"gravado em {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
