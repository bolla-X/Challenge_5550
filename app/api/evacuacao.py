"""Modo Evacuação (M3): iniciar, acompanhar e encerrar, com relatório na cadeia de custódia.

Iniciar e encerrar: supervisor OU o token do palco (`?t=` / corpo `{"t": ...}`,
o mesmo do controle pelo celular — ver `app/api/palco.py`). O token ganha aqui
mais um poder além de trocar a cena (iniciar/encerrar a evacuação); ele continua
sem dar acesso a vídeo, alerta nem contagem. Ver o estado e os relatórios é de
técnico para cima.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from functools import wraps
from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from app.api.palco import _palco
from app.extensions import db
from app.models import ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera
from app.services.evacuacao import (
    AMOSTRA_SERIE_S,
    Evacuacao,
    EvacuacaoInativa,
    EvacuacaoJaAtiva,
    arquivar_relatorio,
    coletar_cameras_info,
    ler_relatorio,
    listar_relatorios,
    numero_do_arquivo,
    pasta_dos_relatorios,
    resumo_do_relatorio,
    ultimo_resumo,
)
from app.utils.auth import current_user, require_role
from app.utils.salas import SALA_PARQUE

logger = logging.getLogger(__name__)

evacuacao_bp = Blueprint("evacuacao", __name__)


def _agora() -> float:
    return time.time()


def _evacuacao() -> Evacuacao:
    extensoes = current_app.extensions
    if "evacuacao" not in extensoes:
        extensoes.setdefault("evacuacao", Evacuacao(AMOSTRA_SERIE_S))
    return extensoes["evacuacao"]


def _supervisor_ou_token(view):
    """Supervisor com sessão, ou o token do palco (sem sessão, como o celular de controle)."""
    exigir_supervisor = require_role(ROLE_SUPERVISOR)(view)

    @wraps(view)
    def wrapper(*args, **kwargs):
        token = request.args.get("t") or (request.get_json(silent=True) or {}).get("t") or ""
        if not token:
            return exigir_supervisor(*args, **kwargs)
        if not hmac.compare_digest(str(token), _palco().token):
            return jsonify({"error": "token inválido"}), 403
        g.evacuacao_por_token = True
        return view(*args, **kwargs)

    return wrapper


def _por() -> str:
    """Quem comandou: só o e-mail da conta (ou a origem, sem conta). Nunca nome nem outro dado."""
    if g.get("evacuacao_por_token"):
        return "palco (token)"
    usuario = current_user()
    return usuario.email if usuario is not None else "sem autenticação"


def _cameras_info() -> list[dict[str, Any]]:
    return coletar_cameras_info(current_app.extensions["monitor_service"])


def _emitir(payload: dict[str, Any]) -> None:
    monitor = current_app.extensions["monitor_service"]
    monitor.socketio.emit("evacuacao", payload, to=SALA_PARQUE)


def _registrar_evento(tipo: str, mensagem: str, severidade: str, por: str, metadata: dict[str, Any]) -> None:
    """Linha do tempo: a evacuação é exatamente o que alguém vai precisar reconstituir depois."""
    from app.repositories.event_repository import EventRepository

    try:
        evento = EventRepository().create(event_type=tipo, message=mensagem, severity=severidade, subject=por, metadata=metadata)
    except Exception as exc:  # noqa: BLE001  (o evento é registro; não impede nem desfaz a evacuação)
        db.session.rollback()
        logger.warning("evacuacao_evento_falhou", extra={"error": str(exc)})
        return
    current_app.extensions["monitor_service"].socketio.emit("timeline_event", evento.to_dict(), to=SALA_PARQUE)


def _amostrar_em_segundo_plano(app, evacuacao: Evacuacao, sessao: int) -> None:
    """Observa as câmeras a cada `EVACUACAO_AMOSTRA_S`, mesmo que ninguém consulte a tela.

    Sem isto, o pico no ponto de encontro dependia de quem estivesse olhando a
    tela naquele segundo. Termina sozinha quando a evacuação (esta sessão) acaba.
    """
    intervalo = max(0.2, float(app.config.get("EVACUACAO_AMOSTRA_S", 1.0)))
    monitor = app.extensions["monitor_service"]
    while evacuacao.ativa and evacuacao.sessao == sessao:
        try:
            with app.app_context():
                evacuacao.observar(coletar_cameras_info(monitor), _agora())
        except Exception as exc:  # noqa: BLE001
            logger.warning("evacuacao_amostra_falhou", extra={"error": str(exc)})
        time.sleep(intervalo)


@evacuacao_bp.post("/api/evacuacao/iniciar")
@_supervisor_ou_token
def iniciar():
    corpo = request.get_json(silent=True) or {}
    ponto = corpo.get("ponto_de_encontro_camera_id")
    if ponto is not None:
        if isinstance(ponto, bool) or not isinstance(ponto, int):
            return jsonify({"error": "ponto_de_encontro_camera_id deve ser o id de uma câmera"}), 400
        if db.session.get(Camera, ponto) is None:
            return jsonify({"error": "câmera do ponto de encontro não encontrada"}), 404
    evacuacao, por, agora = _evacuacao(), _por(), _agora()
    try:
        evacuacao.iniciar(por, ponto, agora)
    except EvacuacaoJaAtiva as exc:
        return jsonify({"error": str(exc), "code": "evacuacao_ja_ativa"}), 409
    _registrar_evento("evacuacao_iniciada", f"Evacuação iniciada por {por}", "critical", por,
                      {"ponto_de_encontro_camera_id": ponto})
    if not current_app.config.get("TESTING"):
        threading.Thread(target=_amostrar_em_segundo_plano, args=(current_app._get_current_object(), evacuacao, evacuacao.sessao),
                         name="evacuacao-amostra", daemon=True).start()
    snapshot = evacuacao.snapshot(_cameras_info(), agora)
    _emitir({"ativa": True, "inicio": snapshot["inicio"], "iniciada_por": por, "ponto_de_encontro_camera_id": ponto})
    return jsonify(snapshot)


@evacuacao_bp.post("/api/evacuacao/encerrar")
@_supervisor_ou_token
def encerrar():
    evacuacao, por, agora = _evacuacao(), _por(), _agora()
    try:
        relatorio = evacuacao.encerrar(por, agora, _cameras_info())
    except EvacuacaoInativa as exc:
        return jsonify({"error": str(exc), "code": "evacuacao_inativa"}), 409
    try:
        caminho, custodia_registrada = arquivar_relatorio(
            relatorio, pasta_dos_relatorios(current_app), custodia_ativa=bool(current_app.config.get("CUSTODIA_ATIVA", True))
        )
    except OSError as exc:
        # A evacuação já fechou em memória: o relatório vai na resposta para não se perder.
        logger.error("evacuacao_relatorio_nao_gravado", extra={"error": str(exc)})
        _emitir({"ativa": False})
        return jsonify({"error": "evacuação encerrada, mas o relatório não pôde ser gravado em disco", "ativa": False,
                        "relatorio": relatorio}), 500
    numero = numero_do_arquivo(caminho)
    completo = relatorio | {"numero": numero}
    _registrar_evento("evacuacao_encerrada", f"Evacuação encerrada por {por} ({relatorio['duracao_s']:.0f} s)", "info", por,
                      {"numero": numero, "sha256": relatorio["sha256"], "arquivo": caminho.name,
                       "chegadas_ponto_de_encontro": relatorio["chegadas_ponto_de_encontro"]})
    _emitir({"ativa": False, "relatorio": resumo_do_relatorio(completo)})
    return jsonify({"ativa": False, "relatorio": completo, "arquivo": caminho.name, "custodia_registrada": custodia_registrada})


@evacuacao_bp.get("/api/evacuacao")
@require_role(ROLE_TECHNICAL)
def estado():
    evacuacao = _evacuacao()
    if not evacuacao.ativa:
        return jsonify({"ativa": False, "ultima": ultimo_resumo(pasta_dos_relatorios(current_app))})
    snapshot = evacuacao.snapshot(_cameras_info(), _agora())
    return jsonify(snapshot)


@evacuacao_bp.get("/api/evacuacao/relatorios")
@require_role(ROLE_TECHNICAL)
def relatorios():
    itens = listar_relatorios(pasta_dos_relatorios(current_app))
    return jsonify({"items": itens, "total": len(itens)})


@evacuacao_bp.get("/api/evacuacao/relatorios/<int:numero>")
@require_role(ROLE_TECHNICAL)
def relatorio(numero: int):
    dados = ler_relatorio(pasta_dos_relatorios(current_app), numero)
    if dados is None:
        return jsonify({"error": "relatório não encontrado"}), 404
    return jsonify(dados)
