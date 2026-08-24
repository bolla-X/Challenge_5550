from __future__ import annotations

import click
from flask import Flask
from flask.cli import AppGroup

from app.models import ROLE_SUPERVISOR, VALID_ROLES, User
from app.services.auth_service import AuthService, WeakPassword

users_cli = AppGroup("users", help="Cria e administra as pessoas que usam o sistema.")


@users_cli.command("create")
@click.option("--email", prompt=True, help="E-mail de login.")
@click.option("--name", prompt="Nome completo", help="Nome exibido na interface.")
@click.option("--role", type=click.Choice(sorted(VALID_ROLES)), default=ROLE_SUPERVISOR, show_default=True)
@click.option("--camera-id", type=int, default=None, help="Câmera do setor (só faz sentido para operator).")
@click.password_option("--password", prompt="Senha", confirmation_prompt="Repita a senha")
def create_user(email: str, name: str, role: str, camera_id: int | None, password: str) -> None:
    """Cria um usuário.

    É por aqui que nasce a PRIMEIRA conta — não existe auto-cadastro pela
    interface, e de propósito: num sistema de segurança do trabalho, quem cria
    acesso é quem já tem acesso.
    """
    try:
        usuario = AuthService().create_user(
            email=email, name=name, password=password, role=role, camera_id=camera_id
        )
    except (WeakPassword, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Criado: {usuario.email} ({usuario.role})")


@users_cli.command("list")
def list_users() -> None:
    usuarios = User.query.order_by(User.name.asc()).all()
    if not usuarios:
        click.echo("Nenhum usuário cadastrado. Crie o primeiro com: flask users create")
        return
    for usuario in usuarios:
        estado = "ativo" if usuario.active else "INATIVO"
        click.echo(f"  {usuario.email:36s} {usuario.role:11s} {estado:8s} {usuario.name}")


@users_cli.command("set-password")
@click.option("--email", prompt=True)
@click.password_option("--password", prompt="Nova senha", confirmation_prompt="Repita a senha")
def set_password(email: str, password: str) -> None:
    usuario = User.query.filter_by(email=email.strip().lower()).first()
    if usuario is None:
        raise click.ClickException(f"Usuário não encontrado: {email}")
    try:
        AuthService().set_password(usuario, password)
    except WeakPassword as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Senha alterada: {usuario.email}")


def register_cli(app: Flask) -> None:
    app.cli.add_command(users_cli)
