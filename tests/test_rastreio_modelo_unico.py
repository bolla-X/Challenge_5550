"""Modo padrão (MULTI_PERSON_DETECTION=false): pessoas do modelo de EPI também são rastreadas.

Regressão: sem ID de rastreio, a projeção de aproximação (F3) nunca disparava
neste modo, e o ID da pessoa era a posição na cena (mudava a cada quadro).
"""

from __future__ import annotations

import threading

import numpy as np
from app import create_app
from app.config import TestConfig
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.schemas import BoundingBox, Detection


class DetectorDuble:
    def __init__(self, deteccoes):
        self.deteccoes = deteccoes

    def detect(self, frame):  # noqa: ARG002
        return list(self.deteccoes)

    def diagnostics(self):
        return {"model_path": "duble.pt", "classes": {}, "error": None}

    def supported_ppe_classes(self):
        return {"helmet", "vest"}


def _pessoa(x):
    return Detection(label="person", confidence=0.9, box=BoundingBox(x, 100, x + 80, 400), category="person")


def test_pessoas_do_modelo_unico_ganham_id_estavel_e_alimentam_a_aproximacao():
    class Cfg(TestConfig):
        MULTI_PERSON_DETECTION = False

    app = create_app(Cfg)
    with app.app_context():
        epi = DetectorDuble([_pessoa(100)])
        recursos = FeatureManager.from_config({"DEFAULT_FEATURES": "ppe,helmet,vest,risk_area"})
        worker = CameraWorker(app, socketio=None, feature_manager=recursos, camera_id=3,
                              source="fonte-falsa", fps=12, detector=epi, person_detector=DetectorDuble([]),
                              pose_estimator=None, inference_lock=threading.Lock())
        quadro = np.zeros((540, 960, 3), dtype=np.uint8)
        ids = []
        for x in (100, 120, 140, 160):  # a mesma pessoa andando para a direita
            epi.deteccoes = [_pessoa(x)]
            analise = worker._inferir(quadro, lambda etapa: None)
            pessoas = [d for d in analise.detections if d.label == "person"]
            assert len(pessoas) == 1
            ids.append(pessoas[0].track_id)
        assert ids[0] is not None and len(set(ids)) == 1, f"ID instável: {ids}"
        assert worker.aproximacao is not None
        worker._atualizar_aproximacao(analise, quadro.shape)  # não pode ignorar a pessoa por falta de ID
        assert ids[0] in worker.aproximacao._trilhas
