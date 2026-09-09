"""Re-bench do fio do LLM, atravessando o `CameraWorker._loop` de verdade.

`scripts/bench_llm.py` mede o DESENHO do serviço: ele chama `submeter()` a
partir de um pipeline próprio, o que era o certo enquanto o fio não existia.
Agora existe, e a pergunta mudou: **ligar a camada custa FPS no worker real?**

Diferenças em relação ao bench_llm.py, e por que importam:

- roda `CameraWorker._loop`, não um laço paralelo. Entram no custo o
  `AlertStateService` (que grava no SQLite dentro do loop), o
  `ComplianceService`, a anotação e a serialização do payload — tudo que a
  BENCH.md declara estar FORA do harness de pipeline. Por isso o FPS aqui é
  menor que o da BENCH.md, e a comparação que vale é LLM on contra LLM off
  **nesta mesma tabela**, não contra a tabela de lá.
- o provedor SIMULA a latência com `sleep`, de propósito e pelo mesmo motivo
  do bench_llm.py: com a API real o número dependeria de rede, cota e humor do
  serviço, e o bench deixaria de ser reprodutível. O que está sob prova é que
  uma chamada lenta — qualquer que seja a origem da lentidão — não segura o
  loop de captura.

Reproduzir:

    python scripts/fetch_fixtures.py
    python scripts/bench_llm_worker.py --frames 250
"""

from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.llm import AnalisadorDeRisco  # noqa: E402
from app.services.camera_worker import CameraWorker  # noqa: E402
from app.services.feature_manager import FeatureManager  # noqa: E402
from app.services.llm_risk_service import ServicoDeRiscoLLM  # noqa: E402
from app.vision.pose_estimator import MediaPipePoseEstimator  # noqa: E402
from app.vision.video_stream import VideoStream  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402

RESPOSTA = (
    '{"nivel_risco": "alto", "epis_ausentes": ["helmet"], '
    '"justificativa": "Trabalhador sem capacete proximo a equipamento em operacao.", '
    '"confianca": 0.82, "acao_recomendada": "Interromper a atividade e fornecer capacete."}'
)


class ProvedorLento:
    """Simula latência de rede. Ver a docstring do módulo para o porquê."""

    def __init__(self, latencia_ms: float) -> None:
        self.latencia_s = latencia_ms / 1000.0
        self.chamadas = 0

    def analisar(self, imagem_jpeg: bytes, prompt: str) -> str:  # noqa: ARG002
        self.chamadas += 1
        time.sleep(self.latencia_s)
        return RESPOSTA


class SocketNulo:
    """Conta emissões sem rede — o custo do `emit` de verdade fica de fora
    aqui, exatamente como na BENCH.md."""

    def __init__(self) -> None:
        self.n = 0

    def emit(self, *_args, **_kwargs) -> None:
        self.n += 1

    def start_background_task(self, target, *args, **kwargs):  # noqa: ARG002
        return None


class RodarAte:
    def __init__(self, continuar) -> None:
        self._continuar = continuar

    def is_set(self) -> bool:
        return bool(self._continuar())

    def set(self) -> None: ...

    def clear(self) -> None:
        self._continuar = lambda: False


def caminho_da_fixture() -> Path:
    caminho = RAIZ / "tests" / "fixtures" / "bench.mp4"
    if not caminho.exists():
        raise SystemExit(
            f"Fixture ausente: {caminho}\nRode primeiro: python scripts/fetch_fixtures.py"
        )
    return caminho


def rodar(argumentos, *, com_llm: bool) -> dict:
    class Cfg(TestConfig):
        YOLO_IMGSZ = argumentos.imgsz
        DETECTION_EVERY_N_FRAMES = argumentos.detect_every_n
        MULTI_PERSON_DETECTION = True
        PPE_MODEL_PATH = str(RAIZ / "models" / "vyra_ppe.pt")
        PERSON_MODEL_PATH = str(RAIZ / "models" / "yolov8n.pt")
        SNAPSHOT_ENABLED = False
        CLEANUP_ON_MONITOR_START = False
        RTSP_FIXTURE_FALLBACK = ""
        TELEMETRY_HZ = 8.0

    app = create_app(Cfg)
    provedor = ProvedorLento(argumentos.latencia_ms)
    servico = ServicoDeRiscoLLM(
        analisador=AnalisadorDeRisco(provedor=provedor),
        debounce_s=argumentos.debounce_s,
        versao="v1",
        habilitado=com_llm,
    )

    with app.app_context():
        db.create_all()
        worker = CameraWorker(
            app,
            socketio=SocketNulo(),
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=1,
            source=str(caminho_da_fixture()),
            fps=1000,  # sem teto artificial: mede o que a maquina aguenta
            width=1280,
            height=720,
            detector=YoloPPEDetector(
                model_path=app.config["PPE_MODEL_PATH"],
                confidence=0.35,
                imgsz=argumentos.imgsz,
                require_person=False,
            ),
            person_detector=YoloPPEDetector(
                model_path=app.config["PERSON_MODEL_PATH"],
                confidence=0.35,
                classes=[0],
                imgsz=argumentos.imgsz,
                require_person=False,
            ),
            pose_estimator=MediaPipePoseEstimator(),
            inference_lock=threading.Lock(),
            servico_llm=servico if com_llm else None,
        )
        # `em_loop`: a fixture tem 210 quadros e o bench pede mais que isso.
        worker.video_stream = VideoStream(
            source=str(caminho_da_fixture()), width=1280, height=720, em_loop=True
        )

        # Instrumenta `submeter` para medir o custo NO CAMINHO DO FRAME.
        custos: list[float] = []
        if com_llm:
            original = servico.submeter

            def cronometrado(**kwargs):
                marca = time.perf_counter()
                try:
                    return original(**kwargs)
                finally:
                    custos.append((time.perf_counter() - marca) * 1000.0)

            worker.servico_llm.submeter = cronometrado  # type: ignore[method-assign]

        worker.start()

        # Aquecimento: a primeira inferencia inclui carga do peso do disco e o
        # warmup do ultralytics. Medida uma vez, ela sozinha domina a media.
        alvo = argumentos.warmup
        worker._running = RodarAte(lambda: worker._frame_counter < alvo)
        worker._loop()
        custos.clear()

        base = worker._frame_counter
        alvo = base + argumentos.frames
        worker._running = RodarAte(lambda: worker._frame_counter < alvo)
        inicio = time.perf_counter()
        worker._loop()
        parede = time.perf_counter() - inicio
        medidos = worker._frame_counter - base

        alertas = len(worker.alert_state_service.active_alerts())
        estatisticas = servico.estatisticas() if com_llm else {}
        worker.stop()
        db.session.remove()
        db.drop_all()

    return {
        "com_llm": com_llm,
        "frames": medidos,
        "parede_s": parede,
        "fps": medidos / parede if parede else 0.0,
        "alertas_ativos": alertas,
        "chamadas_ao_provedor": provedor.chamadas,
        "submeter_p50_ms": statistics.median(custos) if custos else 0.0,
        "submeter_max_ms": max(custos) if custos else 0.0,
        "estatisticas": estatisticas,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--imgsz", type=int, default=416)
    cli.add_argument("--frames", type=int, default=250, help="Frames MEDIDOS.")
    cli.add_argument("--warmup", type=int, default=12, help="Frames fora da estatistica.")
    cli.add_argument("--detect-every-n", type=int, default=3)
    cli.add_argument("--latencia-ms", type=float, default=1500.0)
    cli.add_argument("--debounce-s", type=float, default=15.0)
    argumentos = cli.parse_args()

    # Em serie, NUNCA em paralelo: os dois cenarios disputariam a mesma CPU e
    # contaminariam um ao outro (mesma regra da BENCH.md).
    desligado = rodar(argumentos, com_llm=False)
    ligado = rodar(argumentos, com_llm=True)

    print(
        f"\n=== fio do LLM no worker real (imgsz={argumentos.imgsz}, "
        f"detect_every_n={argumentos.detect_every_n}, latencia simulada="
        f"{argumentos.latencia_ms:.0f} ms) ==="
    )
    print(f"{'':<32}{'LLM desligado':>16}{'LLM ligado':>16}")
    print(f"{'FPS':<32}{desligado['fps']:>16.2f}{ligado['fps']:>16.2f}")
    print(f"{'frames medidos':<32}{desligado['frames']:>16}{ligado['frames']:>16}")
    print(f"{'parede (s)':<32}{desligado['parede_s']:>16.2f}{ligado['parede_s']:>16.2f}")
    print(
        f"{'alertas ativos no fim':<32}{desligado['alertas_ativos']:>16}"
        f"{ligado['alertas_ativos']:>16}"
    )
    print(
        f"{'chamadas ao provedor':<32}{desligado['chamadas_ao_provedor']:>16}"
        f"{ligado['chamadas_ao_provedor']:>16}"
    )
    print(f"{'submeter() p50 (ms)':<32}{'-':>16}{ligado['submeter_p50_ms']:>16.4f}")
    print(f"{'submeter() max (ms)':<32}{'-':>16}{ligado['submeter_max_ms']:>16.4f}")

    est = ligado["estatisticas"]
    print(
        f"\ncontadores do servico: aceitos={est.get('aceitos')} "
        f"descartados_em_voo={est.get('descartados_em_voo')} "
        f"descartados_debounce={est.get('descartados_debounce')} "
        f"invalidos={est.get('invalidos')} "
        f"erros_de_callback={est.get('erros_de_callback')}"
    )

    delta = (ligado["fps"] - desligado["fps"]) / desligado["fps"] * 100 if desligado["fps"] else 0.0
    print(f"\ndelta de FPS: {delta:+.1f}%")
    print("Se o delta for negativo alem do ruido entre execucoes, o fio esta errado:")
    print("submeter() deveria custar microssegundos e a chamada roda fora do loop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
