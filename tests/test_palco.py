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
