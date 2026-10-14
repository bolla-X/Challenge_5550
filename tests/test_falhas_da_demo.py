"""Testes de falha da Fase 4: o que acontece quando algo some no meio da demo.

Já cobertos em outros arquivos (não duplicados aqui):
- fonte inválida / câmera caindo: tests/test_camera_worker_falha_de_fonte.py;
- banco sem tabelas no boot: tests/test_onboarding.py::test_boot_nao_quebra_em_banco_sem_tabela;
- provedor de LLM fora do ar no analisador: tests/test_llm.py::test_provedor_indisponivel_degrada_para_none.
"""

from __future__ import annotations

import time

import numpy as np
from app.extensions import db
from app.models import Camera, User
from app.vision.yolo_ppe_detector import YoloPPEDetector


def test_modelo_ausente_nao_derruba_a_analise(tmp_path):
    detector = YoloPPEDetector(str(tmp_path / "nao-existe.pt"), confidence=0.35)
    quadro = np.zeros((540, 960, 3), dtype=np.uint8)
    assert detector.detect(quadro) == []
    assert detector.diagnostics().get("error"), "o diagnóstico tem de dizer que o modelo falhou"


def test_webcam_ausente_o_portal_usa_a_gravacao(real_monitor_app, monkeypatch):
    import app.demo as demo

    monkeypatch.setattr(demo, "webcam_disponivel", lambda indice=0: False)
    info = demo.semear(real_monitor_app)
    assert info["ao_vivo"] is False
    with real_monitor_app.app_context():
        nomes = {c.name for c in Camera.query.all()}
        assert "Portal" not in nomes
        canteiro = Camera.query.filter_by(name="Canteiro").one()
        assert canteiro.gate_required == ["helmet", "vest"]
        operador = User.query.filter_by(email="operador@demo.local").one()
        assert operador.camera_id == canteiro.id


def test_llm_fora_do_ar_no_resumo_do_relatorio(real_monitor_app, monkeypatch):
    from app.llm import ProvedorGemini, ProvedorIndisponivel

    def falha(self, prompt):
        raise ProvedorIndisponivel("sem rede")

    monkeypatch.setattr(ProvedorGemini, "resumir", falha)
    real_monitor_app.config.update(LLM_ENABLED=True, GEMINI_API_KEY="chave-de-teste")
    cliente = real_monitor_app.test_client()
    assert cliente.post("/api/relatorio/turno/resumo").status_code == 202
    estado = {}
    for _ in range(50):
        estado = cliente.get("/api/relatorio/turno/resumo").get_json()
        if estado.get("estado") != "pendente":
            break
        time.sleep(0.05)
    assert estado["estado"] == "falhou"
    # O relatório em si continua de pé.
    assert cliente.get("/api/relatorio/turno").status_code == 200


def test_banco_indisponivel_aparece_no_checklist(real_monitor_app, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def quebra(*_a, **_k):
        raise OperationalError("SELECT 1", {}, Exception("database is locked"))

    with real_monitor_app.app_context():
        db.session.add(Camera(name="Doca", source_type="USB", source="0"))
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        monkeypatch.setattr(db.session, "execute", quebra)
        checks = monitor.preflight()["checks"]
    banco = next(c for c in checks if c["key"] == "database")
    assert banco["status"] == "error" and "locked" in banco["message"]
