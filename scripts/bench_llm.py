"""Prova que a camada LLM não entra no caminho do frame.

Roda o pipeline de visão sobre a mesma fixture do `bench_pipeline.py`, duas
vezes: com a camada LLM desligada e ligada. O FPS tem que ficar dentro do
ruído. Se cair, o desenho está errado.

    python scripts/bench_llm.py

**O provedor aqui SIMULA latência com `sleep`** (`--latencia-ms`, padrão 1500).
Não é a API real, e o motivo é metodológico: com a API real o número dependeria
de rede, cota e humor do serviço, e o bench deixaria de ser reprodutível. O que
este bench prova é o **desenho assíncrono** — que uma chamada lenta, qualquer
que seja a fonte da lentidão, não segura o loop. A latência real medida contra
o Gemini está em `docs/SPRINT3.md`, gravada pelos goldens.

Mesmo procedimento do bench principal: 12 quadros de aquecimento descartados,
execuções em série, nunca em paralelo.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.llm import AnalisadorDeRisco  # noqa: E402
from app.services.llm_risk_service import ServicoDeRiscoLLM  # noqa: E402
from app.vision.annotator import FrameAnnotator  # noqa: E402
from app.vision.person_tracker import PersonTracker  # noqa: E402
from app.vision.pose_estimator import MediaPipePoseEstimator  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402
from scripts.fetch_fixtures import caminho_da_fixture  # noqa: E402

CLASSES_VYRA = [0, 1, 2, 3, 5, 11, 12, 13]
POLIGONO_RISCO = [(0.70, 0.10), (0.98, 0.10), (0.98, 0.95), (0.70, 0.95)]
FEATURES = dict.fromkeys(
    (
        "ppe",
        "helmet",
        "vest",
        "gloves",
        "glasses",
        "mask",
        "safety_shoe",
        "pose",
        "falls",
        "posture",
        "risk_area",
    ),
    True,
)
OVERLAY = {"boxes": True, "labels": True, "confidence": True, "pose": True, "risk_area": True}

RESPOSTA_SIMULADA = json.dumps(
    {
        "nivel_risco": "alto",
        "epis_ausentes": ["helmet"],
        "justificativa": "Resposta simulada pelo bench; nao ha chamada de rede aqui.",
        "confianca": 0.7,
        "acao_recomendada": "Fornecer capacete antes de retomar a atividade.",
    }
)


class ProvedorLento:
    """Simula a latência de uma chamada multimodal, sem tocar a rede."""

    def __init__(self, latencia_ms: float) -> None:
        self.latencia_s = latencia_ms / 1000.0
        self.chamadas = 0
        self._trava = threading.Lock()

    def analisar(self, imagem_jpeg: bytes, prompt: str) -> str:  # noqa: ARG002
        with self._trava:
            self.chamadas += 1
        time.sleep(self.latencia_s)
        return RESPOSTA_SIMULADA


def rodar(*, com_llm: bool, argumentos) -> dict:
    caminho = caminho_da_fixture("bench")
    detector = YoloPPEDetector(
        model_path=str(RAIZ / "models" / "vyra_ppe.pt"),
        confidence=0.35,
        classes=CLASSES_VYRA,
        imgsz=argumentos.imgsz,
    )
    detector_pessoa = YoloPPEDetector(
        model_path=str(RAIZ / "models" / "yolov8n.pt"),
        confidence=0.35,
        classes=[0],
        imgsz=argumentos.imgsz,
        require_person=False,
    )
    pose = MediaPipePoseEstimator()
    tracker = PersonTracker()
    anotador = FrameAnnotator(POLIGONO_RISCO)

    provedor = ProvedorLento(argumentos.latencia_ms)
    servico = ServicoDeRiscoLLM(
        analisador=AnalisadorDeRisco(provedor=provedor),
        debounce_s=argumentos.debounce_s,
        versao="v1",
        habilitado=com_llm,
    )
    analises: list = []
    servico.ao_concluir = analises.append

    captura = cv2.VideoCapture(str(caminho))
    contador = 0
    cache = None
    frames = 0
    aquecendo = 12
    inicio = time.perf_counter()
    custo_de_submeter = []

    while frames < argumentos.frames:
        ok, quadro = captura.read()
        if not ok:
            captura.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, quadro = captura.read()
            if not ok:
                break

        contador += 1
        nova = not (
            argumentos.detect_every_n > 1 and cache is not None and contador % argumentos.detect_every_n
        )
        if nova:
            deteccoes = detector.detect(quadro)
            pessoas = tracker.update(detector_pessoa.detect(quadro))
            deteccoes = deteccoes + pessoas
            alvos = [(f"person_{p.track_id}", p.track_id, p.box) for p in pessoas]
            poses = pose.estimate_for_people(quadro, alvos, max_people=4) if alvos else []
            if not poses:
                global_pose = pose.estimate(quadro)
                poses = [global_pose] if global_pose.found else []
            cache = (deteccoes, poses)
        deteccoes, poses = cache

        anotado = anotador.annotate(quadro, deteccoes, poses, FEATURES, None, OVERLAY)
        ok_encode, buffer = cv2.imencode(".jpg", anotado, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        jpeg = buffer.tobytes() if ok_encode else b""

        # Aqui está o ponto que o desenho protege: a submissão acontece DENTRO
        # do loop, como aconteceria num evento de alerta criado. O que não pode
        # é ela BLOQUEAR — por isso medimos quanto ela custa.
        if nova and deteccoes:
            marca = time.perf_counter()
            servico.submeter(camera_id=1, imagem_jpeg=jpeg)
            custo_de_submeter.append((time.perf_counter() - marca) * 1000.0)

        if aquecendo > 0:
            aquecendo -= 1
            if aquecendo == 0:
                inicio = time.perf_counter()
                custo_de_submeter.clear()
        else:
            frames += 1

    decorrido = time.perf_counter() - inicio
    captura.release()
    return {
        "com_llm": com_llm,
        "frames": frames,
        "segundos": decorrido,
        "fps": frames / decorrido if decorrido else 0.0,
        "submeter_p50_ms": statistics.median(custo_de_submeter) if custo_de_submeter else 0.0,
        "submeter_max_ms": max(custo_de_submeter) if custo_de_submeter else 0.0,
        "chamadas_ao_provedor": provedor.chamadas,
        "analises_concluidas": len(analises),
        "estatisticas": servico.estatisticas(),
    }


def main() -> int:
    analisador_cli = argparse.ArgumentParser(description="Bench com a camada LLM ligada e desligada.")
    analisador_cli.add_argument("--imgsz", type=int, default=416)
    analisador_cli.add_argument("--frames", type=int, default=300)
    analisador_cli.add_argument("--detect-every-n", type=int, default=3)
    analisador_cli.add_argument("--latencia-ms", type=float, default=1500.0)
    analisador_cli.add_argument("--debounce-s", type=float, default=15.0)
    argumentos = analisador_cli.parse_args()

    print(
        f"fixture: bench.mp4 | imgsz={argumentos.imgsz} | detect_every_n={argumentos.detect_every_n}\n"
        f"provedor SIMULADO com {argumentos.latencia_ms:.0f} ms de latencia (sem rede) | "
        f"debounce={argumentos.debounce_s}s | aquecimento de 12 quadros descartado"
    )

    resultados = []
    for com_llm in (False, True):
        print(f"\n--- {'LLM LIGADO' if com_llm else 'LLM DESLIGADO'} ---")
        resultado = rodar(com_llm=com_llm, argumentos=argumentos)
        resultados.append(resultado)
        estatisticas = resultado["estatisticas"]
        print(f"  FPS                      : {resultado['fps']:.2f}")
        print(f"  frames medidos           : {resultado['frames']}")
        print(
            f"  submeter() p50 / max     : {resultado['submeter_p50_ms']:.3f} / "
            f"{resultado['submeter_max_ms']:.3f} ms"
        )
        print(f"  chamadas ao provedor     : {resultado['chamadas_ao_provedor']}")
        print(f"  analises concluidas      : {resultado['analises_concluidas']}")
        print(f"  aceitos                  : {estatisticas['aceitos']}")
        print(f"  descartados (uma em voo) : {estatisticas['descartados_em_voo']}")
        print(f"  descartados (debounce)   : {estatisticas['descartados_debounce']}")
        print(f"  invalidos                : {estatisticas['invalidos']}")

    desligado, ligado = resultados
    delta = 100 * (ligado["fps"] / desligado["fps"] - 1) if desligado["fps"] else 0.0
    print(f"\nFPS: {desligado['fps']:.2f} (desligado) -> {ligado['fps']:.2f} (ligado)  [{delta:+.1f}%]")
    est = ligado["estatisticas"]
    submetidos = est["aceitos"] + est["descartados_em_voo"] + est["descartados_debounce"]
    print(
        f"Eventos: {submetidos} submetidos, {est['aceitos']} aceitos, "
        f"{submetidos - est['aceitos']} descartados"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
