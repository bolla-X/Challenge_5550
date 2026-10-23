"""Amostra de vídeo versionada da demo (ES Sprint 4, F1.2): entra só no lugar de gravação não baixada."""

from __future__ import annotations

import subprocess

from app import demo_ambiente


def test_amostra_versionada_existe_e_e_leve():
    assert demo_ambiente.AMOSTRA.exists()
    assert demo_ambiente.AMOSTRA.stat().st_size < 2 * 1024 * 1024  # "curta, leve"
    rastreado = subprocess.run(["git", "ls-files", "--error-unmatch", "amostras/canteiro_amostra.mp4"],
                               cwd=demo_ambiente.BASE_DIR, capture_output=True)
    assert rastreado.returncode == 0, "a amostra precisa ser versionada"


def test_gravacao_baixada_vence_a_amostra(tmp_path, monkeypatch):
    (tmp_path / "bench.mp4").write_bytes(b"x")
    monkeypatch.setattr(demo_ambiente, "FIXTURES", tmp_path)

    assert demo_ambiente.fonte_da_gravacao("bench.mp4") == tmp_path / "bench.mp4"


def test_sem_gravacao_a_demo_toca_a_amostra_e_avisa(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(demo_ambiente, "FIXTURES", tmp_path)  # nenhuma gravação baixada
    monkeypatch.setattr(demo_ambiente, "PASTA", tmp_path / "demo")
    monkeypatch.setattr(demo_ambiente, "BANCO", tmp_path / "demo" / "demo.db")
    monkeypatch.setattr(demo_ambiente, "TOKEN", tmp_path / "demo" / "token")
    for chave in ("VISIONEPI_DOTENV", "DEMO_MODE", "DATABASE_URL", "AUTO_CREATE_TABLES", "AUTH_REQUIRED", "HOST", "SECRET_KEY",
                  "LLM_ENABLED", "LLM_DEMO_FALLBACK", "REPLAY_DIR", "SNAPSHOT_DIR", "CLEANUP_ON_MONITOR_START", "ROTULOS_DIR",
                  "TRILHAS_DIR", "SAUDE_VISUAL_DIR", "RTSP_FIXTURE_FALLBACK", "OPCUA_ATIVO", "MQTT_ATIVO",
                  "MQTT_BROKER_EMBUTIDO", "DEFAULT_FEATURES"):
        monkeypatch.delenv(chave, raising=False)  # preparar_ambiente escreve no os.environ; o monkeypatch desfaz

    demo_ambiente.preparar_ambiente()  # antes: SystemExit "gravações ausentes"

    assert demo_ambiente.fonte_da_gravacao("next_multidao.mp4") == demo_ambiente.AMOSTRA
    aviso = capsys.readouterr().out
    assert "Canteiro, Pátio, Escada" in aviso and "amostra" in aviso
