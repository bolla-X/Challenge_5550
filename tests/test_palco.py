"""Modo Apresentação (X6): roteiro único, cena sincronizada e controle por token."""

from __future__ import annotations

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.services.auth_service import AuthService
from app.services.palco import ROTEIRO, Palco

SENHA = "senha-forte-de-teste"


def test_navegacao_nos_limites_do_roteiro():
    p = Palco()
    assert p.publico()["cena"] == 0
    assert p.ir(acao="anterior").cena == 0
    for _ in range(len(ROTEIRO) + 3):
        p.ir(acao="proxima")
    assert p.estado.cena == len(ROTEIRO) - 1
    assert p.publico()["proxima"] is None
    assert p.ir(acao="ir", indice=2).cena == 2
    with pytest.raises(ValueError):
        p.ir(acao="pular")


def test_roteiro_tem_as_cenas_da_missao():
    chaves = [c["chave"] for c in ROTEIRO]
    for chave in ("portal", "enganar", "raiox", "gemeo", "queda", "incidente", "custodia", "simulador", "liga", "retrospectiva"):
        assert chave in chaves
    assert all(c["legenda"] and len(c["legenda"]) <= 110 for c in ROTEIRO)


@pytest.fixture()
def app_auth(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'palco.db'}"

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator", camera_id=1)
    return app


def test_celular_muda_a_cena_so_com_o_token(app_auth):
    celular = app_auth.test_client()
    assert celular.get("/api/palco/estado").status_code == 401
    assert celular.post("/api/palco/ir", json={"acao": "proxima", "t": "errado"}).status_code == 403
    tecnico = app_auth.test_client()
    tecnico.post("/api/auth/login", json={"email": "tec@x.local", "password": SENHA})
    url = tecnico.get("/api/palco/controle").get_json()
    token = url["caminho"].split("t=", 1)[1]
    r = celular.post("/api/palco/ir", json={"acao": "proxima", "t": token}).get_json()
    assert r["cena"] == 1
    # A tela do palco (técnico logado) vê a mesma cena.
    assert tecnico.get("/api/palco/estado").get_json()["cena"] == 1
    assert url["aviso"]  # teste em HTTP: avisa que o celular precisa de --https


def test_operador_nao_comanda_o_palco(app_auth):
    op = app_auth.test_client()
    op.post("/api/auth/login", json={"email": "op@x.local", "password": SENHA})
    assert op.post("/api/palco/ir", json={"acao": "proxima"}).status_code == 403
    assert op.get("/api/palco/controle").status_code == 403


def test_camera_lenta_so_dura_a_cena_da_queda(app_auth, tmp_path, monkeypatch):
    """Entrar na cena "Queda" põe a gravação dela a 0,25× ANTES de responder; sair volta a 1×."""
    import cv2
    import numpy as np
    from app.api import palco as api_palco
    from app.models import Camera

    gravacao = tmp_path / "queda.avi"
    escritor = cv2.VideoWriter(str(gravacao), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for _ in range(10):
        escritor.write(np.zeros((48, 64, 3), dtype=np.uint8))
    escritor.release()
    with app_auth.app_context():
        db.session.add(Camera(name="Queda", source_type="Arquivo", source=str(gravacao), fps=12, width=64, height=48))
        db.session.commit()
        monitor = app_auth.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(Camera.query.filter_by(name="Queda").one().id)
    preparadas = []
    monkeypatch.setattr(api_palco, "_preparar", lambda app, cena: preparadas.append(cena["chave"]))  # sem ligar câmera
    tecnico = app_auth.test_client()
    tecnico.post("/api/auth/login", json={"email": "tec@x.local", "password": SENHA})
    queda = next(i for i, c in enumerate(ROTEIRO) if c["chave"] == "queda")

    assert tecnico.post("/api/palco/ir", json={"acao": "ir", "indice": queda}).status_code == 200
    assert worker.velocidade_gravacao == 0.25
    assert worker.video_state()["velocidade"] == 0.25
    tecnico.post("/api/palco/ir", json={"acao": "proxima"})
    assert worker.velocidade_gravacao == 1.0
