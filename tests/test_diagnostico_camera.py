"""Diagnóstico de tela do `CameraWorker`: FPS real, resolução e classes/30 s.

Por que existe: o FPS que o dashboard mostrava **não era o do pipeline**. O
`dashboardStore.ts` derivava-o do intervalo entre eventos `analysis`, e esses
são emitidos no máximo `TELEMETRY_HZ` vezes por segundo (8, por padrão) — o
número tinha teto em 8 e não distinguia "o pipeline caiu para 6 fps" de "o
pipeline está a 19 e a telemetria está limitada". Em campo é justamente essa a
pergunta que precisa ser respondida em 5 segundos.

Os três casos que importam, e que estes testes travam:

1. **contar só inferência nova.** Com `DETECTION_EVERY_N_FRAMES=3` dois de cada
   três frames reaproveitam as caixas anteriores
   (`tests/test_camera_worker_cache.py`). Contá-los triplicaria a contagem por
   classe sem o modelo ter rodado, e a tela diria que o modelo está vendo três
   vezes mais do que vê.
2. **resolução é a do frame que CHEGOU**, não a pedida no cadastro: em fonte
   RTSP o `CAP_PROP_FRAME_WIDTH` é um pedido que o backend FFMPEG ignora.
3. **a janela desliza:** detecção velha sai da conta sozinha, senão o painel
   viraria um acumulado desde o boot e nunca voltaria a zero.

Nada aqui abre câmera nem carrega peso.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from app import create_app
from app.config import TestConfig
from app.services.camera_worker import JANELA_DETECCOES_S, CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.schemas import BoundingBox, Detection, FrameAnalysis, PoseResult


class DetectorDuble:
    # `confidence` e `max_detections` existem porque `status()` passa por
    # `settings()`, que os le do detector. Sao a superficie que o worker
    # realmente usa; o duble de test_camera_worker_cache.py nao precisa deles
    # porque aquele arquivo nunca chama `status()`.
    confidence = 0.35
    max_detections = 100

    def __init__(self, deteccoes: list[Detection] | None = None) -> None:
        self.chamadas = 0
        self._deteccoes = deteccoes or []

    def detect(self, frame):  # noqa: ARG002
        self.chamadas += 1
        return list(self._deteccoes)

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest", "gloves", "glasses", "mask", "safety_shoe"}


class PoseDuble:
    def estimate(self, frame):  # noqa: ARG002
        return PoseResult(landmarks=[])

    def estimate_for_people(self, frame, people, *, max_people=4):  # noqa: ARG002
        return []


class SocketNulo:
    """`start()` emite; aqui ninguem escuta, e o loop nao chega a subir."""

    def emit(self, *_args, **_kwargs) -> None:
        return None

    def start_background_task(self, target, *args, **kwargs):  # noqa: ARG002
        return None


def deteccao(rotulo: str, track_id: int | None = None) -> Detection:
    return Detection(
        label=rotulo,
        confidence=0.9,
        box=BoundingBox(x1=10, y1=10, x2=110, y2=310),
        category=rotulo,
        track_id=track_id,
    )


@pytest.fixture()
def worker():
    class Cfg(TestConfig):
        DETECTION_EVERY_N_FRAMES = 3
        MULTI_PERSON_DETECTION = False

    app = create_app(Cfg)
    with app.app_context():
        yield CameraWorker(
            app,
            socketio=SocketNulo(),
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=1,
            source="fonte-inexistente-nunca-aberta",
            fps=12,
            detector=DetectorDuble([deteccao("person", track_id=1)]),
            person_detector=DetectorDuble(),
            pose_estimator=PoseDuble(),
            inference_lock=threading.Lock(),
        )


# Substream D1 da Dahua: 4:3, e NAO a resolucao do cadastro (960x540).
FRAME = np.zeros((576, 704, 3), dtype=np.uint8)
ANALISE = FrameAnalysis(
    detections=[deteccao("person"), deteccao("helmet")], pose=None, risk_events=[], poses=[]
)


def test_camera_parada_nao_inventa_numero(worker):
    """Antes do primeiro frame tudo é zero/None — nunca um palpite.

    Um FPS fabricado aqui é pior que nenhum: manda quem está diagnosticando
    procurar problema no modelo quando a fonte sequer abriu.
    """
    diagnostico = worker.diagnostico()

    assert diagnostico["fps"] == 0.0
    assert diagnostico["resolucao"] is None
    assert diagnostico["deteccoes_30s"] == {}


def test_resolucao_e_a_do_frame_recebido_nao_a_do_cadastro(worker):
    """A câmera foi cadastrada 960x540 e a fonte entregou 704x576."""
    worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=True)

    assert worker.diagnostico()["resolucao"] == "704x576"
    assert worker.video_stream.width == 960, "o cadastro segue 960: quem muda é só o diagnóstico"


def test_so_inferencia_nova_conta_na_contagem_por_classe(worker):
    """9 frames de loop, 3 com inferência nova => 3 por classe, não 9.

    É o mesmo reaproveitamento que `test_camera_worker_cache.py` caracteriza.
    Se este número virar 9, a tela passou a contar caixa reaproveitada e
    deixou de significar "o modelo detectou".
    """
    for i in range(9):
        worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=(i % 3 == 0))

    assert worker.diagnostico()["deteccoes_30s"] == {"helmet": 3, "person": 3}


def test_fps_sai_do_loop_e_nao_do_teto_da_telemetria(worker):
    """O loop aqui roda MUITO mais rápido que `TELEMETRY_HZ=8`.

    Se o número voltasse limitado a ~8, seria sinal de que alguém religou o
    cálculo na taxa de emissão — o defeito que este diagnóstico corrige.
    """
    for _ in range(20):
        worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=False)
        time.sleep(0.005)

    fps = worker.diagnostico()["fps"]
    assert fps > 8.0, f"FPS {fps} preso no teto da telemetria em vez do ritmo do loop"


def test_deteccao_velha_sai_da_janela(worker, monkeypatch):
    """Sem isto o painel viraria acumulado desde o boot e nunca zeraria."""
    worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=True)
    assert worker.diagnostico()["deteccoes_30s"]

    # Avanca o relogio alem da janela, em vez de dormir 30 s.
    agora = time.monotonic()
    monkeypatch.setattr(
        "app.services.camera_worker.time.monotonic",
        lambda: agora + JANELA_DETECCOES_S + 1,
    )

    assert worker.diagnostico()["deteccoes_30s"] == {}, "detecção fora da janela ainda contando"


def test_diagnostico_entra_no_status(worker):
    """O card de câmera já consulta `status()` a cada 3 s — o diagnóstico
    viaja junto, sem rota nova."""
    worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=True)

    status = worker.status()

    assert status["diagnostico"]["resolucao"] == "704x576"
    assert status["diagnostico"]["deteccoes_30s"] == {"helmet": 1, "person": 1}


def test_start_zera_o_diagnostico_da_sessao_anterior(worker):
    """Sem isto a tela diria que a câmera está entregando frames antes de ela
    ter entregado o primeiro frame da sessão nova."""
    worker._registrar_diagnostico(FRAME, ANALISE, foi_nova=True)

    worker.start()
    try:
        diagnostico = worker.diagnostico()
    finally:
        worker.stop()

    assert diagnostico["deteccoes_30s"] == {}
    assert diagnostico["resolucao"] is None
