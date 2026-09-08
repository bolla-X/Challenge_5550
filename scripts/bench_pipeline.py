"""Mede o custo por estágio do pipeline de visão, sem Flask e sem rede.

Por que existe: o repositório tem `PROFILE_FRAMES`, que instrumenta o loop de
verdade — mas exige subir o servidor, abrir socket e ter câmera. Isso não é
reproduzível e não é headless. Este harness usa **os mesmos componentes reais**
(`YoloPPEDetector`, `MediaPipePoseEstimator`, `PersonTracker`,
`PersonComplianceMatcher`, `FrameAnnotator`) na **mesma ordem** de
`CameraWorker._loop`, sobre um vídeo fixo.

O que ele NÃO é: não é o worker do Flask. Não há `socketio.emit` real, não há
`AlertStateService` (que grava no banco) nem `ComplianceService`. O estágio
`serializacao` mede o `to_dict()` do payload, que é o custo por frame
atribuível ao preparo da emissão — o envio pela rede fica de fora de propósito,
porque medir rede aqui tornaria o número não reprodutível.

Uso:

    python scripts/bench_pipeline.py --imgsz 416
    python scripts/bench_pipeline.py --imgsz 640 --multi-person
    python scripts/bench_pipeline.py --imgsz 640 --multi-person --cameras 2
    python scripts/bench_pipeline.py --imgsz 640 --multi-person --sem-pose

`--sem-pose` existe para obter o custo do MediaPipe por subtração: a diferença
entre a execução com e sem pose é o orçamento que a pose consome.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.vision.annotator import FrameAnnotator  # noqa: E402
from app.vision.person_compliance_matcher import PPE_KEYS, PersonComplianceMatcher  # noqa: E402
from app.vision.person_tracker import PersonTracker  # noqa: E402
from app.vision.pose_estimator import MediaPipePoseEstimator  # noqa: E402
from app.vision.schemas import FrameAnalysis  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402
from scripts.fetch_fixtures import caminho_da_fixture  # noqa: E402

# Mesmos valores do .env.example, fixados aqui para o bench nao depender do
# .env da maquina de quem roda — senao o numero nao e comparavel.
CLASSES_VYRA = [0, 1, 2, 3, 5, 11, 12, 13]
CONFIANCA = 0.35
QUALIDADE_JPEG = 80
POSE_MAX_PESSOAS = 4
POLIGONO_RISCO = [(0.70, 0.10), (0.98, 0.10), (0.98, 0.95), (0.70, 0.95)]
FEATURES_LIGADAS = dict.fromkeys(
    ("ppe", "helmet", "vest", "gloves", "glasses", "mask", "safety_shoe", "pose", "falls", "posture", "risk_area"),
    True,
)
OVERLAY = {"boxes": True, "labels": True, "confidence": True, "pose": True, "risk_area": True}

ORDEM_ESTAGIOS = (
    "leitura",
    "espera_lock",
    "yolo_epi",
    "yolo_pessoa",
    "tracking",
    "pose",
    "matching",
    "anotacao",
    "encode",
    "serializacao",
)


class Cronometro:
    """Coleta amostras por estagio. Uma instancia por camera."""

    def __init__(self) -> None:
        self.amostras: dict[str, list[float]] = defaultdict(list)
        self.fim_a_fim: list[float] = []
        # Enquanto False, o relogio anda mas nada e gravado — e assim que o
        # aquecimento fica de fora da estatistica sem deixar de ser executado.
        self.gravando = False
        self._t = 0.0
        self._inicio_frame = 0.0

    def frame_comeca(self) -> None:
        agora = time.perf_counter()
        self._t = agora
        self._inicio_frame = agora

    def marca(self, estagio: str) -> None:
        agora = time.perf_counter()
        if self.gravando:
            self.amostras[estagio].append((agora - self._t) * 1000.0)
        self._t = agora

    def frame_termina(self) -> None:
        if self.gravando:
            self.fim_a_fim.append((time.perf_counter() - self._inicio_frame) * 1000.0)


def percentis(valores: list[float]) -> dict[str, float]:
    if not valores:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0, "n": 0}
    ordenados = sorted(valores)
    indice_p95 = min(len(ordenados) - 1, int(round(0.95 * (len(ordenados) - 1))))
    return {
        "p50": statistics.median(ordenados),
        "p95": ordenados[indice_p95],
        "max": ordenados[-1],
        "n": len(ordenados),
    }


def custo_da_copia(frame) -> float:
    """Mede `frame.copy()` isolado — a copia morta de video_stream.py:198.

    Nao faz parte do loop; e medida a parte para quantificar quanto custa uma
    linha que hoje ninguem le.
    """
    amostras = []
    for _ in range(30):
        marca = time.perf_counter()
        frame.copy()
        amostras.append((time.perf_counter() - marca) * 1000.0)
    return statistics.median(amostras)


def rodar_camera(
    indice: int,
    caminho_video: Path,
    detector: YoloPPEDetector,
    detector_pessoa: YoloPPEDetector | None,
    pose_estimator: MediaPipePoseEstimator | None,
    trava: threading.Lock,
    argumentos,
    resultado: dict,
    barreira: threading.Barrier | None,
) -> None:
    cronometro = Cronometro()
    tracker = PersonTracker()
    matcher = PersonComplianceMatcher()
    anotador = FrameAnnotator(POLIGONO_RISCO)
    suportados = dict.fromkeys(PPE_KEYS, True)

    captura = cv2.VideoCapture(str(caminho_video))
    if not captura.isOpened():
        raise SystemExit(f"Nao consegui abrir {caminho_video}")

    contador_deteccao = 0
    analise_em_cache: FrameAnalysis | None = None
    frames = 0
    # Aquecimento: a PRIMEIRA inferencia inclui carga do peso do disco,
    # alocacao de buffers e o warmup interno do ultralytics — medida uma vez,
    # ela sozinha vira o "max" de todo o relatorio e contamina o p95. Os frames
    # de aquecimento rodam o pipeline inteiro, mas nao entram na estatistica.
    aquecendo = argumentos.warmup
    if barreira is not None:
        barreira.wait()
    inicio = time.perf_counter()

    while frames < argumentos.frames:
        cronometro.frame_comeca()
        ok, frame = captura.read()
        if not ok:
            # Fixture curta: reinicia para completar a contagem de frames pedida.
            captura.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = captura.read()
            if not ok:
                break
        cronometro.marca("leitura")

        contador_deteccao += 1
        pula = (
            argumentos.detect_every_n > 1
            and analise_em_cache is not None
            and contador_deteccao % argumentos.detect_every_n != 0
        )

        if pula:
            analise = analise_em_cache
        else:
            # `espera_lock` medido SEPARADO de `yolo_epi` de proposito: sem isso
            # o tempo parado esperando outra camera soltar o lock apareceria
            # como se fosse custo de inferencia, e a conclusao sobre contencao
            # sairia errada.
            with trava:
                cronometro.marca("espera_lock")
                deteccoes = detector.detect(frame)
                cronometro.marca("yolo_epi")
                if detector_pessoa is not None:
                    pessoas_cruas = detector_pessoa.detect(frame)
                    cronometro.marca("yolo_pessoa")
                    deteccoes = deteccoes + tracker.update(pessoas_cruas)
                    cronometro.marca("tracking")
                poses = []
                if pose_estimator is not None:
                    pessoas = [d for d in deteccoes if d.label == "person" or d.category == "person"]
                    pessoas.sort(key=lambda d: d.track_id if d.track_id is not None else 0)
                    alvos = [
                        (f"person_{d.track_id}" if d.track_id is not None else f"person_{i}", d.track_id, d.box)
                        for i, d in enumerate(pessoas, start=1)
                    ]
                    if alvos:
                        poses = pose_estimator.estimate_for_people(frame, alvos, max_people=POSE_MAX_PESSOAS)
                    if not poses:
                        global_pose = pose_estimator.estimate(frame)
                        poses = [global_pose] if global_pose.found else []
                    cronometro.marca("pose")
            analise = FrameAnalysis(
                detections=deteccoes, pose=poses[0] if poses else None, risk_events=[], poses=poses
            )
            analise_em_cache = analise

        matcher.build(
            analise.detections,
            supported_ppe=suportados,
            enabled_ppe=suportados,
            risk_polygon=POLIGONO_RISCO,
            frame_shape=frame.shape,
        )
        cronometro.marca("matching")

        anotado = anotador.annotate(
            frame,
            analise.detections,
            analise.poses or ([analise.pose] if analise.pose else []),
            FEATURES_LIGADAS,
            None,
            OVERLAY,
        )
        cronometro.marca("anotacao")

        ok_encode, buffer = cv2.imencode(".jpg", anotado, [int(cv2.IMWRITE_JPEG_QUALITY), QUALIDADE_JPEG])
        if ok_encode:
            buffer.tobytes()
        cronometro.marca("encode")

        analise.to_dict()
        cronometro.marca("serializacao")

        cronometro.frame_termina()
        if aquecendo > 0:
            aquecendo -= 1
            if aquecendo == 0:
                # Zera o relogio de parede junto: FPS efetivo tem que refletir
                # o regime permanente, nao a carga do modelo.
                cronometro.gravando = True
                inicio = time.perf_counter()
        else:
            frames += 1

    decorrido = time.perf_counter() - inicio
    captura.release()
    resultado[indice] = {
        "frames": frames,
        "segundos": decorrido,
        "fps_efetivo": frames / decorrido if decorrido else 0.0,
        "estagios": {e: percentis(cronometro.amostras.get(e, [])) for e in ORDEM_ESTAGIOS},
        "fim_a_fim": percentis(cronometro.fim_a_fim),
    }


def main() -> int:
    analisador = argparse.ArgumentParser(description="Bench por estagio do pipeline de visao.")
    analisador.add_argument("--imgsz", type=int, default=416)
    analisador.add_argument("--multi-person", action="store_true", help="Liga o segundo YOLO (COCO) + tracker.")
    analisador.add_argument("--sem-pose", action="store_true", help="Desliga o MediaPipe (custo por subtracao).")
    analisador.add_argument("--cameras", type=int, default=1)
    analisador.add_argument("--frames", type=int, default=300, help="Frames MEDIDOS por camera.")
    analisador.add_argument("--warmup", type=int, default=12, help="Frames de aquecimento, fora da estatistica.")
    analisador.add_argument("--detect-every-n", type=int, default=3)
    analisador.add_argument("--modelo", default="models/vyra_ppe.pt", help="Peso de EPI (.pt ou .onnx).")
    analisador.add_argument("--modelo-pessoa", default="models/yolov8n.pt")
    analisador.add_argument("--rotulo", default="", help="Nome do cenario no relatorio.")
    analisador.add_argument("--json", default="", help="Grava o resultado bruto neste arquivo.")
    argumentos = analisador.parse_args()

    try:
        import torch

        threads_torch = torch.get_num_threads()
    except Exception:
        threads_torch = -1

    caminho_video = caminho_da_fixture("bench")
    sonda = cv2.VideoCapture(str(caminho_video))
    fps_entrada = sonda.get(cv2.CAP_PROP_FPS)
    largura = int(sonda.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(sonda.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, primeiro = sonda.read()
    sonda.release()
    ms_copia = custo_da_copia(primeiro) if ok else 0.0

    detector = YoloPPEDetector(
        model_path=str(RAIZ / argumentos.modelo),
        confidence=CONFIANCA,
        classes=CLASSES_VYRA,
        imgsz=argumentos.imgsz,
    )
    detector_pessoa = None
    if argumentos.multi_person:
        detector_pessoa = YoloPPEDetector(
            model_path=str(RAIZ / argumentos.modelo_pessoa),
            confidence=CONFIANCA,
            classes=[0],
            imgsz=argumentos.imgsz,
            require_person=False,
        )
    pose_estimator = None if argumentos.sem_pose else MediaPipePoseEstimator()

    # Um lock global para todas as cameras — exatamente como MonitorService.
    trava = threading.Lock()
    resultado: dict[int, dict] = {}
    barreira = threading.Barrier(argumentos.cameras) if argumentos.cameras > 1 else None
    threads = [
        threading.Thread(
            target=rodar_camera,
            args=(i, caminho_video, detector, detector_pessoa, pose_estimator, trava, argumentos, resultado, barreira),
        )
        for i in range(argumentos.cameras)
    ]

    rotulo = argumentos.rotulo or (
        f"imgsz={argumentos.imgsz} multi_person={argumentos.multi_person} "
        f"pose={not argumentos.sem_pose} cameras={argumentos.cameras}"
    )
    print(f"\n=== {rotulo} ===")
    print(f"fixture: {caminho_video.name} ({largura}x{altura}, {fps_entrada:.2f} fps de entrada)")
    print(f"modelo EPI: {argumentos.modelo} | detect_every_n={argumentos.detect_every_n}")
    print(f"torch.get_num_threads(): {threads_torch} | cv2.getNumThreads(): {cv2.getNumThreads()}")
    print(f"frame.copy() isolado (1 frame {largura}x{altura}): {ms_copia:.3f} ms (mediana de 30)")

    inicio = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    total = time.perf_counter() - inicio

    print(f"\n{'estagio':<14} {'p50 ms':>9} {'p95 ms':>9} {'max ms':>9} {'n':>7}")
    print("-" * 52)
    for estagio in ORDEM_ESTAGIOS:
        colunas = [resultado[i]["estagios"][estagio] for i in sorted(resultado)]
        if not any(c["n"] for c in colunas):
            continue
        p50 = statistics.mean(c["p50"] for c in colunas if c["n"])
        print(
            f"{estagio:<14} {p50:>9.2f} {max(c['p95'] for c in colunas):>9.2f} "
            f"{max(c['max'] for c in colunas):>9.2f} {sum(c['n'] for c in colunas):>7}"
        )

    fim = [resultado[i]["fim_a_fim"] for i in sorted(resultado)]
    print("-" * 52)
    print(
        f"{'FIM-A-FIM':<14} {statistics.mean(c['p50'] for c in fim):>9.2f} "
        f"{max(c['p95'] for c in fim):>9.2f} {max(c['max'] for c in fim):>9.2f} "
        f"{sum(c['n'] for c in fim):>7}"
    )

    fps_por_camera = [resultado[i]["fps_efetivo"] for i in sorted(resultado)]
    total_frames = sum(resultado[i]["frames"] for i in sorted(resultado))
    # O agregado usa a janela MEDIDA (pos-aquecimento) mais longa entre as
    # cameras, nao o relogio de parede do processo — senao a carga do modelo
    # entraria na conta e o agregado nao bateria com a soma dos por-camera.
    janela = max(resultado[i]["segundos"] for i in sorted(resultado))
    print(
        f"\nFPS efetivo por camera: {', '.join(f'{f:.2f}' for f in fps_por_camera)}"
        f"  | agregado: {total_frames / janela:.2f} fps"
    )
    print(
        f"FPS de entrada da fixture: {fps_entrada:.2f} | janela medida: {janela:.1f}s "
        f"| parede total (com aquecimento): {total:.1f}s | frames medidos: {total_frames}"
    )

    if argumentos.json:
        Path(argumentos.json).write_text(
            json.dumps(
                {
                    "rotulo": rotulo,
                    "imgsz": argumentos.imgsz,
                    "multi_person": argumentos.multi_person,
                    "pose": not argumentos.sem_pose,
                    "cameras": argumentos.cameras,
                    "modelo": argumentos.modelo,
                    "detect_every_n": argumentos.detect_every_n,
                    "torch_threads": threads_torch,
                    "ms_frame_copy": ms_copia,
                    "fps_entrada": fps_entrada,
                    "fps_agregado": total_frames / janela,
                    "janela_medida_s": janela,
                    "parede_s": total,
                    "por_camera": resultado,
                },
                indent=2,
                default=float,
            ),
            encoding="utf-8",
        )
        print(f"JSON: {argumentos.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
