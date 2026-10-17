"""Modo Apresentação (X6): roteiro, cena atual e controle pelo celular.

`/api/palco/estado` e `/api/palco/ir` aceitam sessão de técnico/supervisor OU
o token do QR (`?t=`), porque o celular não tem login. O token só muda a cena
do palco — não dá acesso a vídeo, alerta nem dado nenhum. (A cena "Evacuação" usa o
mesmo token para acionar e encerrar a evacuação: ver `app/api/evacuacao.py`.)

Trocar de cena dispara, em UMA thread, a saída da cena anterior (`saida`) e o
preparo da nova (`preparo`, `reiniciar`). Falha de qualquer um vira log e uma
legenda de contingência (`fallback` em `/api/palco/estado`); o palco segue.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time

from flask import Blueprint, current_app, jsonify, request

from app.models import ROLE_TECHNICAL, Camera
from app.services import palco_preparos
from app.services.palco import ROTEIRO, Palco, camera_da_cena, cameras_pausadas
from app.utils.auth import current_user, login_required, require_role

logger = logging.getLogger(__name__)

palco_bp = Blueprint("palco", __name__)

# Uma troca de cena por vez: sair de uma (encerrar a permissão, a evacuação) e
# entrar na outra não se atropelam quando o apresentador passa as cenas rápido.
_transicoes = threading.Lock()
_dormir = time.sleep  # costura para o teste não esperar o relógio


def _palco() -> Palco:
    palco = current_app.extensions.get("palco")
    if palco is None:
        palco = current_app.extensions["palco"] = Palco()
    return palco


def _negado():
    """None = pode; senão a resposta de erro (401 sem sessão nem token, 403 token/papel errado)."""
    token = request.args.get("t") or (request.get_json(silent=True) or {}).get("t") or ""
    if token:
        return None if hmac.compare_digest(str(token), _palco().token) else (jsonify({"error": "token inválido"}), 403)
    if not current_app.config.get("AUTH_REQUIRED", True):
        return None
    usuario = current_user()
    if usuario is None:
        return jsonify({"error": "Autenticação necessária.", "code": "unauthenticated"}), 401
    return None if usuario.has_role(ROLE_TECHNICAL) else (jsonify({"error": "Seu tipo de conta não permite esta ação."}), 403)


def _cameras_por_nome() -> dict[str, int]:
    return {c.name: c.id for c in Camera.query.all()}


def _cameras_ao_vivo() -> frozenset[int]:
    """Câmeras que não são gravação (webcam, RTSP, celular): a cena "Tape a câmera" só reage nelas."""
    return frozenset(c.id for c in Camera.query.all() if c.source_type != "Arquivo")


def _camera_da_cena(cena: dict, por_nome: dict[str, int] | None = None, ao_vivo: frozenset[int] | None = None) -> int | None:
    por_nome = _cameras_por_nome() if por_nome is None else por_nome
    if ao_vivo is None:
        ao_vivo = _cameras_ao_vivo() if cena.get("ao_vivo") else frozenset()
    return camera_da_cena(cena, por_nome, ao_vivo)


@palco_bp.get("/api/palco/roteiro")
@login_required
def roteiro():
    por_nome = _cameras_por_nome()
    ao_vivo = _cameras_ao_vivo()
    cenas = []
    for cena in ROTEIRO:
        camera_id = _camera_da_cena(cena, por_nome, ao_vivo)
        extra = {"camera_id": camera_id}
        if cena.get("ao_vivo"):
            extra["camera_ao_vivo"] = camera_id in ao_vivo  # falso = a cena toca uma gravação e avisa
        cenas.append(cena | extra)
    return jsonify({"cenas": cenas, "estado": _palco().publico()})


@palco_bp.get("/api/palco/estado")
def estado():
    negado = _negado()
    if negado:
        return negado
    palco = _palco()
    pausadas: list[str] = []
    # Só a TELA do palco (sessão, sem token) sustenta a pausa: o celular de
    # controle não segura câmeras pausadas se o palco for fechado.
    if not request.args.get("t"):
        pausadas = _aplicar_ativas(ROTEIRO[palco.estado.cena])
    return jsonify(palco.publico() | {"pausadas": pausadas})


def _aplicar_ativas(cena: dict) -> list[str]:
    """Pausa as câmeras fora da cena (e renova o lease). Devolve os nomes pausados."""
    por_nome = _cameras_por_nome()
    pausar = cameras_pausadas(cena, por_nome, _cameras_ao_vivo() if cena.get("ao_vivo") else frozenset())
    current_app.extensions["monitor_service"].pausar_pelo_palco(pausar)
    return sorted(nome for nome, cid in por_nome.items() if cid in pausar)


def _ajustar_velocidades(cena: dict) -> None:
    """Câmera lenta só dura a cena: a câmera dela toca na velocidade pedida, as outras a 1×.

    Síncrono (é só um atributo): quando a tela da cena consulta o status, a
    velocidade já é a nova — o rótulo nunca mostra 1× com o vídeo lento, nem o contrário.
    """
    por_nome = _cameras_por_nome()
    alvo = _camera_da_cena(cena, por_nome)
    monitor = current_app.extensions["monitor_service"]
    for camera_id in por_nome.values():
        try:
            worker = monitor.worker_da_camera(camera_id)
        except LookupError:
            continue
        velocidade = float(cena.get("velocidade", 1.0)) if camera_id == alvo else 1.0
        if velocidade != worker.velocidade_gravacao:
            worker.tocar_gravacao(velocidade, cena.get("inicio_s", 0.0) if camera_id == alvo else 0.0)


def _reiniciar_gravacao(app, cena: dict) -> str | None:
    """A gravação recomeça (do início ou de `inicio_s`), para o evento cair sempre no mesmo segundo."""
    camera_id = _camera_da_cena(cena)
    if camera_id is None:
        return None
    try:
        worker = app.extensions["monitor_service"].worker_da_camera(camera_id)
    except LookupError:
        return None
    worker.stop()
    # O stop solta a fonte; a posição inicial vale na reabertura.
    if cena.get("inicio_s"):
        worker.tocar_gravacao(worker.velocidade_gravacao, cena["inicio_s"])
    worker.start()
    return None


def _referencia_visual(app, cena: dict) -> str | None:
    """"Tape a câmera": a referência de saúde visual da câmera da cena é refeita agora."""
    camera_id = _camera_da_cena(cena)
    if camera_id is None:
        return "Nenhuma câmera cadastrada para esta cena."
    return palco_preparos.redefinir_referencia_visual(app.extensions["monitor_service"], camera_id, dormir=_dormir)


def _permissao_de_demonstracao(app, cena: dict) -> str | None:
    """"Permissão com vigia": emite a PT de demonstração na câmera da cena (idempotente)."""
    camera_id = _camera_da_cena(cena)
    if camera_id is None:
        return "A câmera da cena não está cadastrada: não há onde emitir a permissão de demonstração."
    palco_preparos.abrir_permissao_de_demonstracao(camera_id)
    return None


def _encerrar_evacuacao_do_palco(app, cena: dict) -> None:
    from app.api.evacuacao import encerrar_a_do_palco  # import tardio: app.api.evacuacao importa este módulo

    encerrar_a_do_palco()


def _encerrar_permissao_de_demonstracao(app, cena: dict) -> None:
    palco_preparos.encerrar_permissoes_de_demonstracao()


# O que o roteiro (`preparo` / `saida`) chama pelo nome. Cada preparo devolve None
# ou o texto de contingência que a tela mostra no lugar da legenda.
_PREPAROS = {"referencia_visual": _referencia_visual, "permissao_demo": _permissao_de_demonstracao}
_SAIDAS = {"encerrar_evacuacao": _encerrar_evacuacao_do_palco, "encerrar_permissao_demo": _encerrar_permissao_de_demonstracao}


def _preparar(app, cena: dict) -> None:
    """Gatilho determinístico da cena, em thread. Nunca levanta: falha vira log + legenda de contingência."""
    nomes = (["reiniciar_gravacao"] if cena.get("reiniciar") else []) + list(cena.get("preparo") or [])
    with app.app_context():
        for nome in nomes:
            try:
                passo = _reiniciar_gravacao if nome == "reiniciar_gravacao" else _PREPAROS[nome]
                fallback = passo(app, cena)
            except Exception:  # noqa: BLE001  (o palco segue; a legenda de contingência diz o que não está acontecendo)
                logger.exception("palco_preparo_falhou", extra={"cena": cena["chave"], "preparo": nome})
                fallback = palco_preparos.FALHA_DE_PREPARO
            if fallback:
                _palco().registrar_fallback(cena["chave"], fallback)


def _ao_sair(app, cena: dict) -> None:
    """O que a cena desfaz ao sair (permissão de demonstração, evacuação do palco). Também nunca levanta."""
    with app.app_context():
        for nome in cena.get("saida") or []:
            try:
                _SAIDAS[nome](app, cena)
            except Exception:  # noqa: BLE001
                logger.exception("palco_saida_falhou", extra={"cena": cena["chave"], "saida": nome})


def _transicao(app, saindo: dict, entrando: dict) -> None:
    """Sai de uma cena e prepara a outra, uma troca por vez. Pula o preparo se o apresentador já seguiu adiante."""
    with _transicoes:
        _ao_sair(app, saindo)
        if ROTEIRO[app.extensions["palco"].estado.cena]["chave"] == entrando["chave"]:
            _preparar(app, entrando)


@palco_bp.post("/api/palco/ir")
def ir():
    negado = _negado()
    if negado:
        return negado
    corpo = request.get_json(silent=True) or {}
    palco = _palco()
    anterior = palco.estado.cena
    try:
        novo = palco.ir(acao=str(corpo.get("acao", "")), indice=corpo.get("indice"))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    if novo.cena != anterior:
        _aplicar_ativas(ROTEIRO[novo.cena])
        _ajustar_velocidades(ROTEIRO[novo.cena])
        # Em thread: reiniciar a gravação leva ~1–2 s e o celular não espera.
        threading.Thread(
            target=_transicao, args=(current_app._get_current_object(), ROTEIRO[anterior], ROTEIRO[novo.cena]), daemon=True
        ).start()
    return jsonify(palco.publico())


@palco_bp.get("/api/palco/controle")
@require_role(ROLE_TECHNICAL)
def controle():
    """URL do controle (para o QR da tela do palco)."""
    from app.api.celular import _ip_da_lan

    palco = _palco()
    caminho = f"/palco/controle?t={palco.token}"
    porta = request.host.rsplit(":", 1)[-1] if ":" in request.host else ("443" if request.is_secure else "80")
    ip = _ip_da_lan()
    esquema = "https" if request.is_secure else "http"
    return jsonify({
        "caminho": caminho,
        "url_lan": f"{esquema}://{ip}:{porta}{caminho}" if ip else None,
        "https": request.is_secure,
        "aviso": None if request.is_secure else
        "Servidor em HTTP só nesta máquina: para o celular alcançar, rode python run.py --demo --https.",
    })
