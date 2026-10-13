"""Publicação sem análise nova reaproveita regras/conformidade; sala vazia não serializa.

Medido no batata 4 câm. (docs/NEXT2026/BENCHMARKS.md): o loop refazia regras,
conformidade e `to_dict()` (com as poses da multidão) a cada quadro de vídeo,
para o MESMO resultado. E o python-socketio 5.16.4 serializa o pacote antes de
olhar quem está na sala, então emitir para sala vazia custava o JSON inteiro.
"""

from __future__ import annotations

import threading

import numpy as np
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.utils.salas import emitir_para_camera, emitir_para_foco
from app.vision.schemas import BoundingBox, Detection, FrameAnalysis


class DetectorDuble:
    def detect(self, frame):  # noqa: ARG002
        return []

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest"}


def _worker(app):
    return CameraWorker(
        app, socketio=app.extensions["monitor_service"].socketio,
        feature_manager=FeatureManager.from_config(app.config), camera_id=5, source="fonte-falsa", fps=12,
        detector=DetectorDuble(), person_detector=DetectorDuble(), pose_estimator=None, inference_lock=threading.Lock(),
    )


def test_quadros_sem_analise_nova_nao_refazem_regras(real_monitor_app, monkeypatch):
    with real_monitor_app.app_context():
        worker = _worker(real_monitor_app)
        chamadas = {"n": 0}
        original = worker.rule_engine.analyze

        def contando(*a, **k):
            chamadas["n"] += 1
            return original(*a, **k)

        monkeypatch.setattr(worker.rule_engine, "analyze", contando)
        pessoa = Detection(label="person", confidence=0.9, box=BoundingBox(10, 10, 110, 310), category="person", track_id=1)
        analise = FrameAnalysis(detections=[pessoa], pose=None, risk_events=[], poses=[])
        quadro = np.zeros((540, 960, 3), dtype=np.uint8)

        worker._publicar(quadro, analise, True, 0.0)
        primeiro = worker.latest_analysis()
        for _ in range(5):
            worker._publicar(quadro, analise, False, 0.0)

        assert chamadas["n"] == 1, "a mesma análise foi reavaliada a cada quadro"
        assert worker.stats.resumo(30)["totais"]["publicacoes_reaproveitadas"] == 5
        assert worker.latest_analysis()["compliance"] == primeiro["compliance"]

        nova = FrameAnalysis(detections=[pessoa], pose=None, risk_events=[], poses=[])
        worker._publicar(quadro, nova, True, 0.0)
        assert chamadas["n"] == 2, "análise nova sempre é avaliada"


class _Gerente:
    def __init__(self, salas):
        self.rooms = {"/": salas}


class _SocketComSalas:
    def __init__(self, salas):
        self.server = type("S", (), {"manager": _Gerente(salas)})()
        self.emitidos = []

    def emit(self, evento, payload, to=None):
        self.emitidos.append((evento, to))


def test_sala_vazia_nao_recebe_emit():
    socket = _SocketComSalas({"parque": {"sid1": "eio1"}, "foco:3": {}})
    emitir_para_foco(socket, "analysis", {"x": 1}, 3)
    emitir_para_camera(socket, "alert_created", {"x": 1}, 3)
    assert socket.emitidos == [("alert_created", "parque")]


def test_sem_estrutura_de_salas_emite_como_antes():
    class Dummy:
        def __init__(self):
            self.emitidos = []

        def emit(self, evento, payload, to=None):
            self.emitidos.append((evento, to))

    socket = Dummy()
    emitir_para_foco(socket, "analysis", {}, 3)
    emitir_para_camera(socket, "alert_created", {}, 3)
    assert socket.emitidos == [("analysis", "foco:3"), ("alert_created", "parque"), ("alert_created", "camera:3")]
