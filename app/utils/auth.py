from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import current_app, g, jsonify, session

from app.extensions import db
from app.models import ROLE_LEVELS, ROLE_OPERATOR, User

SESSION_USER_KEY = "user_id"
SESSION_EPOCH_KEY = "epoch"


def current_user() -> User | None:
    """Usuario da sessao, carregado no maximo uma vez por request.

    Sessao assinada com SECRET_KEY (cookie HttpOnly). Se a pessoa for
    desativada ou apagada, o proximo request ja nao encontra o registro e a
    sessao morre sozinha — nao existe token valido fora do banco.
    """
    if "usuario_atual" in g:
        return g.usuario_atual

    user_id = session.get(SESSION_USER_KEY)
    usuario = None
    if user_id is not None:
        candidato = db.session.get(User, user_id)
        epoca_do_cookie = session.get(SESSION_EPOCH_KEY)
        if candidato is not None and candidato.active and epoca_do_cookie == candidato.session_epoch:
            usuario = candidato
        else:
            # Pessoa apagada, desativada, ou epoca antiga (senha trocada /
            # sessoes revogadas). O cookie deixa de valer aqui, nao no cliente.
            session.clear()

    g.usuario_atual = usuario
    return usuario


def login_user(user: User) -> None:
    session.clear()  # evita fixacao de sessao: id novo a cada login
    session[SESSION_USER_KEY] = user.id
    session[SESSION_EPOCH_KEY] = user.session_epoch
    session.permanent = True
    g.usuario_atual = user


def logout_user() -> None:
    """Encerra a sessao NESTE navegador.

    Nao incrementa a epoca de proposito: derrubar todas as sessoes a cada
    logout expulsaria a pessoa do kiosk do chao de fabrica quando ela saisse
    no desktop. Para revogar em todos os lugares (conta comprometida), o
    caminho e trocar a senha — que chama `revoke_sessions`.
    """
    session.clear()
    g.usuario_atual = None


def auth_enabled() -> bool:
    return bool(current_app.config.get("AUTH_REQUIRED", True))


def login_required(view: Callable[..., Any] | None = None, *, sempre: bool = False) -> Callable[..., Any]:
    """Exige sessao.

    `sempre=True` ignora AUTH_REQUIRED. Use nas views que DEPENDEM do objeto do
    usuario (`current_user()`): com a flag desligada elas recebiam None e
    estouravam 500 em vez de responder 401.
    """

    def decorator(alvo: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(alvo)
        def wrapper(*args, **kwargs):
            if not sempre and not auth_enabled():
                return alvo(*args, **kwargs)
            if current_user() is None:
                return jsonify({"error": "Autenticação necessária.", "code": "unauthenticated"}), 401
            return alvo(*args, **kwargs)

        return wrapper

    return decorator(view) if view is not None else decorator


def require_role(minimo: str, *, sempre: bool = False) -> Callable[..., Any]:
    """Exige papel >= `minimo`. Hierarquico: supervisor passa onde tecnico passa.

    Devolve 403 (nao 404) quando a pessoa esta autenticada mas sem privilegio —
    ela ja sabe que o recurso existe, esconder so atrapalha.
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args, **kwargs):
            # `sempre=True` ignora AUTH_REQUIRED: usado nas rotas que CRIAM
            # acesso. Com a flag desligada, POST /api/users deixaria qualquer
            # um se promover a supervisor.
            if not sempre and not auth_enabled():
                return view(*args, **kwargs)
            usuario = current_user()
            if usuario is None:
                return jsonify({"error": "Autenticação necessária.", "code": "unauthenticated"}), 401
            if usuario.level < ROLE_LEVELS.get(minimo, 99):
                return (
                    jsonify(
                        {
                            "error": "Seu perfil não permite esta ação.",
                            "code": "forbidden",
                            "required_role": minimo,
                            "your_role": usuario.role,
                        }
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapper

    return decorator


def camera_scope() -> int | None:
    """A qual câmera a pessoa logada está restrita, ou None se vê todas.

    Só o Operador é restrito, e à câmera do setor dele (`User.camera_id`).
    Técnico e Supervisor precisam ver o parque inteiro para configurar e
    supervisionar, então não têm escopo.

    Com a autenticação desligada (suíte de teste das rotas antigas) ninguém é
    restrito — não há sessão de onde tirar o setor.
    """
    if not auth_enabled():
        return None
    usuario = current_user()
    if usuario is None or usuario.role != ROLE_OPERATOR:
        return None
    return usuario.camera_id


def camera_permitida(camera_id: int | None) -> bool:
    escopo = camera_scope()
    if escopo is None:
        return _operador_sem_setor() is False
    return camera_id == escopo


def _operador_sem_setor() -> bool:
    """Operador sem câmera atribuída ainda.

    Não vê NADA até o supervisor definir o setor. Deixar passar seria pior que
    o problema que este módulo resolve: a conta existiria com acesso amplo
    justamente por estar incompleta.
    """
    if not auth_enabled():
        return False
    usuario = current_user()
    return usuario is not None and usuario.role == ROLE_OPERATOR and usuario.camera_id is None


def escopo_ou_erro():
    """Para as rotas LEGADAS, que operam sobre "a câmera padrão".

    Devolve `(camera_id, None)` — onde `camera_id=None` significa "a padrão",
    o comportamento de sempre para Técnico e Supervisor. Para o Operador,
    devolve a câmera do setor dele: sem isso, `/status` e `/video_feed` o
    levariam à câmera de menor id, que pode ser de outra área.

    Operador ainda sem setor recebe `(None, erro)` — não a câmera padrão.
    """
    if _operador_sem_setor():
        return None, erro_fora_do_escopo()
    return camera_scope(), None


def erro_fora_do_escopo():
    """Resposta padrão para câmera fora do setor da pessoa.

    404, não 403: para o Operador aquela câmera simplesmente não existe. Um 403
    confirmaria que ela existe e que ele não pode vê-la — informação que ele não
    precisa ter sobre o parque de outra área.
    """
    if _operador_sem_setor():
        return (
            jsonify(
                {
                    "error": "Sua conta ainda não tem câmera atribuída. Peça ao supervisor.",
                    "code": "sem_camera_atribuida",
                }
            ),
            403,
        )
    return jsonify({"error": "câmera não encontrada"}), 404
