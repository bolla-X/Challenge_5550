"""Cena "Queda" do palco (ADENDO 2 da MISSÃO 2): gravação em câmera lenta.

A queda da gravação fica ~0,8 s no chão; em tempo real, duas análises seguidas
(a regra de emergência, que não muda) não cabem nisso numa máquina sem GPU
dedicada. O palco toca a gravação a 0,25× a partir de um segundo próximo da
queda, e a tela mostra a velocidade que o servidor informa.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np
import pytest
from app.services.agendador_de_inferencia import AgendadorDeInferencia
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.services.palco import ROTEIRO
from app.vision.video_stream import VideoStream


class DetectorDuble:
    model_path = "duble.pt"

    def detect(self, frame):  # noqa: ARG002
        return []

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest"}


def _gravacao(caminho, fps: int = 10, segundos: int = 2) -> str:
    """Vídeo em que o brilho do quadro i é 10·i: a posição lida sai do pixel."""
    escritor = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"MJPG"), fps, (64, 48))
    for i in range(fps * segundos):
        escritor.write(np.full((48, 64, 3), min(255, 10 * i), dtype=np.uint8))
    escritor.release()
    return str(caminho)


def _worker(app, fonte: str, agendador=None) -> CameraWorker:
    return CameraWorker(
        app,
        socketio=app.extensions["monitor_service"].socketio,
        feature_manager=FeatureManager.from_config(app.config),
        camera_id=42,
        source=fonte,
        fps=12,
        detector=DetectorDuble(),
        person_detector=DetectorDuble(),
        pose_estimator=None,
        inference_lock=threading.Lock(),
        agendador=agendador,
    )


def test_a_cena_da_queda_pede_um_quarto_da_velocidade_perto_da_queda():
    cena = next(c for c in ROTEIRO if c["chave"] == "queda")
    assert cena["velocidade"] == 0.25
    assert 0 < cena["inicio_s"] < 6.2  # a queda da gravação começa em ~6,2 s
    assert cena["reiniciar"] and "Queda" in cena["camera"]


def test_video_stream_abre_a_gravacao_no_segundo_pedido_uma_vez(tmp_path):
    fonte = _gravacao(tmp_path / "g.avi")
    stream = VideoStream(fonte, 64, 48, em_loop=True)
    stream.inicio_ms = 1000.0
    ok, quadro = stream.read()
    assert ok and abs(int(quadro.mean()) - 100) <= 12  # quadro 10 (1 s a 10 fps)
    assert stream.inicio_ms == 0.0  # vale uma vez: a volta do loop é do início
    stream.release()


def test_gravacao_lenta_tem_ritmo_fixo_mesmo_com_espectador_e_na_confirmacao(real_monitor_app, tmp_path):
    agendador = AgendadorDeInferencia()
    worker = _worker(real_monitor_app, _gravacao(tmp_path / "g.avi"), agendador)
    worker.video_stream.fps_da_fonte = 25.0
    worker.espectadores = 1
    assert worker._ritmo_de_gravacao() is None  # com espectador: tempo real
    assert worker.tocar_gravacao(0.25, 4.0)
    assert worker.velocidade_gravacao == 0.25 and worker.video_stream.inicio_ms == 4000.0
    assert worker._ritmo_de_gravacao() == pytest.approx(6.25)
    # Confirmação de emergência em curso: o ritmo NÃO cai para os 4 fps dela —
    # o rótulo "0,25×" tem de continuar verdadeiro.
    agendador._prioridade_ate[42] = float("inf")
    assert worker._ritmo_de_gravacao() == pytest.approx(6.25)
    assert worker.video_state()["velocidade"] == 0.25
    worker.tocar_gravacao(1.0)
    assert worker._ritmo_de_gravacao() == pytest.approx(4.0)  # volta à regra da confirmação
    assert worker.video_state()["velocidade"] == 1.0


def test_camera_ao_vivo_nao_anda_devagar(real_monitor_app):
    worker = _worker(real_monitor_app, "rtsp://127.0.0.1:1/x")
    assert not worker.tocar_gravacao(0.25, 4.0)
    assert worker.velocidade_gravacao == 1.0
    assert worker.video_state()["velocidade"] == 1.0
