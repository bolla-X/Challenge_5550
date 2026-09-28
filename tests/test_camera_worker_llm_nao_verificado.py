"""Segundo gatilho do LLM (Sprint 4): pessoa "nao verificada" que persiste.

Com PPE_MISSING_POLICY=evidencia, pessoa cujo capacete nao foi visto (nem com,
nem sem) fica "unverified" e NAO gera alerta. E exatamente o caso em que a
Sprint 3 mostrou o LLM acrescentando algo: distinguir ausente de nao visivel
(SPRINT3.md, cena segura). Entao o LLM passa a ser chamado tambem ai — uma vez,
quando o estado se confirma pelo mesmo numero de deteccoes que confirma um
alerta — e continua sem criar, resolver ou suprimir alerta.
"""

from __future__ import annotations

import threading

import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.services.camera_worker import CameraWorker
from app.services.feature_manager import FeatureManager
from app.vision.schemas import BoundingBox, Detection

from test_camera_worker_llm import (
    DetectorDuble,
    FonteQueEntrega,
    PoseDuble,
    ServicoLLMDuble,
    SocketDuble,
    pessoa,
    rodar,
)

CABECA = BoundingBox(x1=40, y1=10, x2=80, y2=40)


def _montar(monkeypatch, deteccoes, *, politica="evidencia", apos=3):
    class Cfg(TestConfig):
        ALERT_CREATE_AFTER_FRAMES = apos
        MULTI_PERSON_DETECTION = False
        SNAPSHOT_ENABLED = False
        CLEANUP_ON_MONITOR_START = False
        RTSP_FIXTURE_FALLBACK = ""
        PPE_MISSING_POLICY = politica

    app = create_app(Cfg)
    servico = ServicoLLMDuble()
    with app.app_context():
        db.create_all()
        worker = CameraWorker(
            app,
            socketio=SocketDuble(),
            feature_manager=FeatureManager.from_config(app.config),
            camera_id=3,
            source="duble://entrega",
            fps=12,
            detector=DetectorDuble(deteccoes),
            person_detector=DetectorDuble(),
            pose_estimator=PoseDuble(),
            inference_lock=threading.Lock(),
            servico_llm=servico,
        )
        worker.video_stream = FonteQueEntrega()
        monkeypatch.setattr("app.services.camera_worker.time.sleep", lambda _s: None)
        yield worker, servico
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def so_pessoa(monkeypatch):
    yield from _montar(monkeypatch, [pessoa()])


def test_nao_verificado_confirmado_submete_uma_vez(so_pessoa):
    worker, servico = so_pessoa
    rodar(worker, 2)
    assert servico.submissoes == [], "antes de confirmar (3 deteccoes) nao gasta chamada"
    rodar(worker, 10)
    assert len(servico.submissoes) == 1, f"estado persistente submeteu {len(servico.submissoes)} vezes"


def test_nao_verificado_nao_cria_alerta(so_pessoa):
    worker, _servico = so_pessoa
    rodar(worker, 6)
    ativos = worker.alert_state_service.active_alerts()
    assert [a for a in ativos if a.get("rule", "").startswith("missing_")] == []


def test_negativa_detectada_cria_alerta_e_submete_pelo_caminho_antigo(monkeypatch):
    sem_capacete = Detection(label="no_helmet", confidence=0.8, box=CABECA, category="ppe_negativo")
    for worker, servico in _montar(monkeypatch, [pessoa(), sem_capacete], apos=1):
        rodar(worker, 3)
        regras = {a.get("rule") for a in worker.alert_state_service.active_alerts()}
        assert "missing_helmet" in regras
        assert len(servico.submissoes) == 1


def test_politica_ausencia_nao_usa_o_gatilho_novo(monkeypatch):
    """Na politica antiga nada fica "unverified": o gatilho e so o de sempre."""
    for worker, servico in _montar(monkeypatch, [pessoa()], politica="ausencia", apos=1):
        rodar(worker, 12)
        assert len(servico.submissoes) == 1
