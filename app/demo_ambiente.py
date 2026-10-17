"""Ambiente da demo, preparado ANTES de qualquer import do pacote `app`.

O `Config` lê as variáveis de ambiente no import; por isso este arquivo não
importa nada de `app` e o `run.py` o carrega pelo caminho (importar `app.*`
executaria o `app/__init__.py`, que importa o `Config` cedo demais).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
PASTA = BASE_DIR / "instance" / "demo"
BANCO = PASTA / "demo.db"
TOKEN = PASTA / "token"
FIXTURES = BASE_DIR / "tests" / "fixtures"

# Câmeras da demo: (nome, setor, arquivo). O setor é o que o Modo TV agrega.
GRAVACOES = [
    ("Canteiro", "Obra", "bench.mp4"),
    ("Pátio", "Expedição", "next_multidao.mp4"),
    ("Escada", "Manutenção", "next_queda.mp4"),
]
# Sem webcam, o Portal toca esta gravação: um trabalhador de capacete e colete
# de frente, de perto (ADENDO 3 da MISSÃO 2). Sem ela (fixtures antigas), o
# Portal recua para a gravação do Canteiro, como antes.
GRAVACAO_DO_PORTAL = ("Portal", "Portaria", "portal.mp4")
# Todos os EPIs exigidos ligados na demo (MISSÃO 2, P0.2). Antes eram só
# capacete, colete e luvas: cada EPI somava UM alerta por pessoa na tela. Com os
# alertas agrupados em incidentes por (câmera, regra, zona), a multidão com os 7
# EPIs mostra no máximo 1 incidente por regra e zona (medido:
# bench/results/incidentes-depois-multidao-*.json). Calçado e protetor auricular
# não são detectados pelo modelo: aparecem como "não suportado", nunca como falta.
EPIS_DESLIGADOS_NA_DEMO: tuple[str, ...] = ()


# Zona de risco do Pátio: faixa da direita (onde os pedestres entram).
ZONA_PATIO = [[0.62, 0.30], [0.98, 0.30], [0.98, 0.98], [0.62, 0.98]]
# Calibração de DEMONSTRAÇÃO das três gravações numa planta só (G5/X1): o
# trapézio do chão de cada vídeo vai para um setor diferente do galpão. É uma
# aproximação feita a olho (as gravações não são da mesma fábrica), e a tela
# do gêmeo mostra posições, não medidas.
_CHAO_NO_VIDEO = [[0.05, 0.55], [0.95, 0.55], [0.98, 0.98], [0.02, 0.98]]
PLANTA_PATIO = {"pontos_camera": _CHAO_NO_VIDEO, "pontos_planta": [[0.42, 0.08], [0.95, 0.08], [0.95, 0.62], [0.42, 0.62]]}
PLANTAS = {
    "Canteiro": {"pontos_camera": _CHAO_NO_VIDEO, "pontos_planta": [[0.05, 0.08], [0.37, 0.08], [0.37, 0.52], [0.05, 0.52]]},
    "Pátio": PLANTA_PATIO,
    "Escada": {"pontos_camera": _CHAO_NO_VIDEO, "pontos_planta": [[0.05, 0.60], [0.37, 0.60], [0.37, 0.92], [0.05, 0.92]]},
}
# Missões da equipe por turno (X8), como um supervisor configuraria.
MISSOES = [
    {"titulo": "5 check-ins liberados no portal", "tipo": "checkin_portal", "alvo": 5},
    {"titulo": "Reconhecer 3 incidentes em até 1 minuto", "tipo": "reconhecido_rapido", "alvo": 3},
    {"titulo": "Revisar 10 recortes na fila de rótulos", "tipo": "rotulo", "alvo": 10},
    {"titulo": "60 minutos conformes na planta", "tipo": "minuto_conforme", "alvo": 60},
]
METAS = {"Obra": {"minutos_conformes": 30, "checkins_portal": 5}, "Portaria": {"minutos_conformes": 30, "checkins_portal": 10}}


def preparar_ambiente() -> None:
    """Antes do `create_app()`: banco novo e configuração da demo no ambiente."""
    faltando = [arq for _, _, arq in GRAVACOES if not (FIXTURES / arq).exists()]
    if faltando:
        raise SystemExit(f"[demo] gravações ausentes em tests/fixtures: {', '.join(faltando)}. "
                         "Rode uma vez, com internet: python scripts/fetch_fixtures.py")
    PASTA.mkdir(parents=True, exist_ok=True)
    for arquivo in (BANCO, Path(str(BANCO) + "-journal"), Path(str(BANCO) + "-wal"), Path(str(BANCO) + "-shm")):
        try:
            if arquivo.exists():
                arquivo.unlink()
        except PermissionError:
            raise SystemExit("[demo] o banco da demo está em uso: já há uma demo rodando? Feche-a e tente de novo.") from None
    for sub in ("clips", "snapshots", "rotulos", "trilhas", "referencias"):
        shutil.rmtree(PASTA / sub, ignore_errors=True)
    os.environ.update({
        "VISIONEPI_DOTENV": "0",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite:///{BANCO.as_posix()}",
        "AUTO_CREATE_TABLES": "true",
        "AUTH_REQUIRED": "true",
        "SECRET_KEY": secrets.token_hex(32),
        "LLM_ENABLED": "false",
        "REPLAY_DIR": str(PASTA / "clips"),
        "SNAPSHOT_DIR": str(PASTA / "snapshots"),
        # A demo já apaga snapshots e clipes ao subir e no reset. Limpar a cada
        # câmera ligada apagava evidência que está na cadeia de custódia (X3) —
        # e a cena da queda no palco reinicia a câmera.
        "CLEANUP_ON_MONITOR_START": "false",
        "ROTULOS_DIR": str(PASTA / "rotulos"),
        "TRILHAS_DIR": str(PASTA / "trilhas"),
        "SAUDE_VISUAL_DIR": str(PASTA / "referencias"),
        "RTSP_FIXTURE_FALLBACK": "",
        # M2: a demo mostra a integração industrial offline (OPC UA + broker MQTT embutido).
        "OPCUA_ATIVO": os.environ.get("OPCUA_ATIVO", "true"),
        "MQTT_ATIVO": os.environ.get("MQTT_ATIVO", "true"),
        "MQTT_BROKER_EMBUTIDO": os.environ.get("MQTT_BROKER_EMBUTIDO", "true"),
        "DEFAULT_FEATURES": "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,ear_protection,"
                            "pose,falls,posture,risk_area,sos,ergonomia,imobilidade",
    })
    TOKEN.write_text(secrets.token_urlsafe(32), encoding="utf-8")


def resetar_pelo_terminal(porta: int) -> dict[str, Any]:
    """`flask demo reset`: pede ao servidor da demo; sem servidor, limpa o banco direto."""
    inicio = time.monotonic()
    if TOKEN.exists():
        pedido = urllib.request.Request(f"http://127.0.0.1:{porta}/api/demo/reset", method="POST", data=b"{}",
                                        headers={"X-Demo-Token": TOKEN.read_text(encoding="utf-8").strip(),
                                                 "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resposta:
                return json.loads(resposta.read()) | {"via": "servidor"}
        except (urllib.error.URLError, OSError):
            pass  # servidor fora do ar: segue para o banco
    if not BANCO.exists():
        raise SystemExit("[demo] não há banco da demo. Rode: python run.py --demo")
    with sqlite3.connect(BANCO) as conexao:
        conexao.execute("DELETE FROM alerts")
        conexao.execute("DELETE FROM event_logs")
        for tabela in ("incidentes", "custodia", "liga_pontos"):
            if conexao.execute("SELECT name FROM sqlite_master WHERE name=?", (tabela,)).fetchone():
                conexao.execute(f"DELETE FROM {tabela}")
    for sub in ("clips", "snapshots", "trilhas"):
        shutil.rmtree(PASTA / sub, ignore_errors=True)
    return {"ok": True, "segundos": round(time.monotonic() - inicio, 2), "via": "banco (servidor fora do ar)"}
