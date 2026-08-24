from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import current_app, g, jsonify, session

from app.extensions import db
from app.models import ROLE_LEVELS, User

SESSION_USER_KEY = "user_id"


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
        if candidato is not None and candidato.active:
            usuario = candidato
        else:
            session.pop(SESSION_USER_KEY, None)

    g.usuario_atual = usuario
    return usuario


def login_user(user: User) -> None:
    session.clear()  # evita fixacao de sessao: id novo a cada login
    session[SESSION_USER_KEY] = user.id
    session.permanent = True
    g.usuario_atual = user


def logout_user() -> None:
    session.clear()
    g.usuario_atual = None


def auth_enabled() -> bool:
    return bool(current_app.config.get("AUTH_REQUIRED", True))


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not auth_enabled():
            return view(*args, **kwargs)
        if current_user() is None:
            return jsonify({"error": "Autenticação necessária.", "code": "unauthenticated"}), 401
        return view(*args, **kwargs)

    return wrapper


def require_role(minimo: str) -> Callable[..., Any]:
    """Exige papel >= `minimo`. Hierarquico: supervisor passa onde tecnico passa.

    Devolve 403 (nao 404) quando a pessoa esta autenticada mas sem privilegio —
    ela ja sabe que o recurso existe, esconder so atrapalha.
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not auth_enabled():
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
