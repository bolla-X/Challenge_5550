"""Modo demonstração: reset pelo terminal, autorização do reset e tema claro."""

from __future__ import annotations

import sqlite3

import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db


class DemoConfig(TestConfig):
    DEMO_MODE = True


@pytest.fixture()
def demo_app(tmp_path, monkeypatch):
    import app.api.demo as api_demo

    token = tmp_path / "token"
    token.write_text("segredo-local", encoding="utf-8")
    monkeypatch.setattr(api_demo, "TOKEN", token)
    chamadas = []
    monkeypatch.setattr(api_demo, "resetar_no_servidor", lambda app: chamadas.append(1) or {"ok": True, "segundos": 0.1})
    app = create_app(DemoConfig)
    with app.app_context():
        db.create_all()
        app.chamadas_reset = chamadas
        yield app


def test_reset_exige_token_local_ou_supervisor(demo_app):
    cliente = demo_app.test_client()
    assert cliente.post("/api/demo/reset").status_code == 403
    assert cliente.post("/api/demo/reset", headers={"X-Demo-Token": "errado"}).status_code == 403
    r = cliente.post("/api/demo/reset", headers={"X-Demo-Token": "segredo-local"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert demo_app.chamadas_reset == [1]


def test_rota_de_reset_nao_existe_fora_da_demo(client):
    assert client.post("/api/demo/reset").status_code == 404


def test_tema_claro_so_na_demo(demo_app, client):
    assert "visionepi-theme','light'" in demo_app.test_client().get("/").get_data(as_text=True)
    assert "visionepi-theme','light'" not in client.get("/").get_data(as_text=True)


def test_reset_pelo_terminal_sem_servidor_limpa_o_banco(tmp_path, monkeypatch):
    import app.demo_ambiente as amb

    banco = tmp_path / "demo.db"
    with sqlite3.connect(banco) as c:
        c.execute("CREATE TABLE alerts (id INTEGER)")
        c.execute("CREATE TABLE event_logs (id INTEGER)")
        c.execute("INSERT INTO alerts VALUES (1)")
        c.execute("INSERT INTO event_logs VALUES (1)")
    monkeypatch.setattr(amb, "BANCO", banco)
    monkeypatch.setattr(amb, "PASTA", tmp_path)
    monkeypatch.setattr(amb, "TOKEN", tmp_path / "sem-token")
    r = amb.resetar_pelo_terminal(porta=1)
    assert r["ok"] and "banco" in r["via"]
    with sqlite3.connect(banco) as c:
        assert c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM event_logs").fetchone()[0] == 0


def test_demo_desliga_os_epis_que_so_fazem_ruido():
    from app.demo import EPIS_DESLIGADOS_NA_DEMO, _features_da_demo

    f = _features_da_demo()
    assert all(not f[k] for k in EPIS_DESLIGADOS_NA_DEMO)
    assert f["helmet"] and f["vest"] and f["falls"]
