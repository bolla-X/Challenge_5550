"""Vídeo de câmera sem espectador publica devagar; análise nova sai na hora.

Medido no perfil batata com 4 câmeras (docs/NEXT2026/BENCHMARKS.md): publicar
a 12 fps câmeras que ninguém assistia (resize + regras + emissão por quadro)
deixava a análise ~2x mais lenta. O agendador agora também só prepara (resize)
o quadro que vai de fato inferir.
"""

from __future__ import annotations

import threading
import time

import numpy as np
from app.services.agendador_de_inferencia import AgendadorDeInferencia
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.schemas import FrameAnalysis


class DetectorDuble:
    model_path = "duble.pt"

    def detect(self, frame):  # noqa: ARG002
        return []

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest"}


def test_agendador_prepara_so_o_quadro_que_infere():
    agendador = AgendadorDeInferencia()
    liberar = threading.Event()
    preparados: list[int] = []
    analisados: list[tuple] = []
    entregue = threading.Event()

    def analisar(frame, marcar):  # noqa: ARG001
        liberar.wait(2.0)
        analisados.append(frame)
        return frame

    def entregar(resultado, ts):  # noqa: ARG001
        entregue.set()

    def preparar(frame):
        preparados.append(frame)
        return ("preparado", frame)

    agendador.registrar(1, analisar, entregar, preparar=preparar)
    try:
        agendador.submeter(1, 0, 0.0)
        time.sleep(0.2)  # o quadro 0 já está sendo analisado (bloqueado)
        for i in range(1, 6):
            agendador.submeter(1, i, 0.0)  # só o 5 sobrevive no slot
        liberar.set()
        limite = time.monotonic() + 3
        while len(analisados) < 2 and time.monotonic() < limite:
            time.sleep(0.02)
    finally:
        agendador.parar()

    assert analisados[:2] == [("preparado", 0), ("preparado", 5)]
    assert preparados == [0, 5], "os quadros sobrescritos no slot não foram preparados"


class FonteRapida:
    """Entrega quadros sem cadência (não é arquivo): ~200 fps."""

    def __init__(self) -> None:
        self.quadro = np.zeros((54, 96, 3), dtype=np.uint8)
        self.width, self.height = 96, 54

    def read(self):
        time.sleep(0.005)
        return True, self.quadro

    def status(self):
        return type("S", (), {"to_dict": lambda self: {}})()

    def release(self):
        pass


def _rodar(worker, segundos: float) -> dict:
    worker.stats.limpar()
    worker._running.set()
    t = threading.Thread(target=worker._loop_assincrono, daemon=True)
    t.start()
    time.sleep(segundos)
    worker._running.clear()
    t.join(3)
    return worker.stats.resumo(30)["totais"]


def test_sem_espectador_publica_devagar_mas_analise_nova_sai_na_hora(real_monitor_app):
    real_monitor_app.config["VIDEO_FPS_SEM_ESPECTADOR"] = 2.0
    agendador = AgendadorDeInferencia()
    worker = CameraWorker(
        real_monitor_app,
        socketio=real_monitor_app.extensions["monitor_service"].socketio,
        feature_manager=FeatureManager.from_config(real_monitor_app.config),
        camera_id=99,
        source="fonte-falsa",
        fps=12,
        detector=DetectorDuble(),
        person_detector=DetectorDuble(),
        pose_estimator=None,
        inference_lock=threading.Lock(),
        agendador=agendador,
    )
    worker.video_stream = FonteRapida()
    # Inferência falsa de ~0,3 s, sempre "nova".
    agendador.registrar(
        99,
        lambda frame, marcar: (time.sleep(0.3), FrameAnalysis(detections=[], pose=None, risk_events=[], poses=[]))[1],
        worker._receber_analise,
        stats=worker.stats,
        preparar=worker._preparar_quadro,
    )
    try:
        worker.espectadores = 0
        sem = _rodar(worker, 2.0)
        worker.espectadores = 1
        com = _rodar(worker, 2.0)
    finally:
        agendador.parar()

    # Sem espectador: ~2 fps de vídeo + as análises novas (~3/s) furando a fila.
    assert sem.get("frames_publicados", 0) <= 2 * 2 + sem.get("analises_publicadas", 0) + 2
    assert sem.get("analises_publicadas", 0) >= 4, "análise nova não pode esperar a cadência do vídeo"
    # Com espectador: o teto de 12 fps de antes.
    assert com.get("frames_publicados", 0) >= 18
