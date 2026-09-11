from __future__ import annotations

import click
from flask import Flask, current_app
from flask.cli import AppGroup

from app.config import CAMINHO_RTSP_PADRAO, montar_url_rtsp
from app.extensions import db
from app.llm import redigir_segredos
from app.models import DEFAULT_CAMERA_FEATURES, ROLE_SUPERVISOR, VALID_ROLES, Camera, User
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


cameras_cli = AppGroup("cameras", help="Cadastra e lista as câmeras monitoradas.")


@cameras_cli.command("add")
@click.option("--name", prompt="Nome da câmera", help="Nome exibido na interface.")
@click.option("--host", default=None, help="IP/host de uma câmera RTSP (a URL é montada aqui).")
@click.option("--fonte", default=None, help="Fonte que não é RTSP: índice USB ('0'), caminho de arquivo ou URL pronta.")
@click.option("--canal", type=int, default=1, show_default=True, help="Canal da câmera (Dahua: começa em 1).")
@click.option("--subtype", type=int, default=None, help="0 = stream principal, 1 = substream. Default: RTSP_SUBTYPE (1).")
@click.option("--porta", type=int, default=None, help="Porta RTSP. Default: RTSP_PORTA (554).")
@click.option("--local", default=None, help="Localização física, para a interface.")
@click.option("--fps", type=int, default=12, show_default=True)
@click.option("--largura", type=int, default=960, show_default=True)
@click.option("--altura", type=int, default=540, show_default=True)
@click.option(
    "--rotacao",
    type=click.Choice(["0", "90", "180", "270"]),
    default="0",
    show_default=True,
    help="Graus pra corrigir câmera montada física de lado/invertida.",
)
def add_camera(
    name: str,
    host: str | None,
    fonte: str | None,
    canal: int,
    subtype: int | None,
    porta: int | None,
    local: str | None,
    fps: int,
    largura: int,
    altura: int,
    rotacao: str,
) -> None:
    """Cadastra uma câmera.

    NÃO EXISTE `--usuario` NEM `--senha`, de propósito. Argumento de linha de
    comando fica no histórico do shell e aparece em `ps aux` para qualquer
    usuário da máquina; senha de rede industrial de terceiro não pode viver
    ali. A credencial vem de `RTSP_USUARIO`/`RTSP_SENHA` no `.env`, que é
    ignorado pelo git — e sai redigida de tudo que é impresso.

    Endereço de câmera é DADO, não código: nenhuma câmera da planta está
    embutida em módulo nenhum (travado por tests/test_cameras_cli.py).
    """
    if bool(host) == bool(fonte):
        raise click.ClickException("Informe --host (câmera RTSP) OU --fonte (USB/arquivo/URL pronta), não os dois.")

    if host:
        usuario = str(current_app.config.get("RTSP_USUARIO", "") or "")
        senha = str(current_app.config.get("RTSP_SENHA", "") or "")
        if not (usuario and senha):
            raise click.ClickException(
                "RTSP_USUARIO e RTSP_SENHA não estão no .env. Sem credencial a câmera "
                "seria cadastrada e nunca conectaria. Preencha os dois no .env (não no "
                ".env.example, que é versionado) e rode de novo."
            )
        source = montar_url_rtsp(
            host=host,
            usuario=usuario,
            senha=senha,
            porta=porta if porta is not None else int(current_app.config.get("RTSP_PORTA", 554)),
            canal=canal,
            subtype=subtype if subtype is not None else int(current_app.config.get("RTSP_SUBTYPE", 1)),
            caminho=str(current_app.config.get("RTSP_CAMINHO", CAMINHO_RTSP_PADRAO)),
        )
        source_type = "RTSP"
    else:
        source = str(fonte)
        # Mesma distinção de fonte que Camera.source_type já documenta.
        source_type = "USB" if source.isdigit() else ("RTSP" if source.startswith("rtsp://") else "Arquivo")

    camera = Camera(
        name=name.strip()[:120],
        location=(local.strip()[:160] if local else None),
        source_type=source_type,
        source=source[:255],
        fps=max(1, min(60, fps)),
        width=largura,
        height=altura,
        rotation=int(rotacao),
        features_json=dict(DEFAULT_CAMERA_FEATURES),
    )
    db.session.add(camera)
    db.session.commit()
    # `redigir_segredos` e nao a URL crua: esta linha vai pro terminal e
    # costuma acabar copiada num log de setup.
    click.echo(f"Câmera {camera.id} cadastrada: {camera.name} -> {redigir_segredos(camera.source)}")


@cameras_cli.command("list")
def list_cameras() -> None:
    cameras = Camera.query.order_by(Camera.id.asc()).all()
    if not cameras:
        click.echo("Nenhuma câmera cadastrada. Cadastre a primeira com: flask --app wsgi cameras add")
        return
    for camera in cameras:
        estado = "ativa" if camera.enabled else "INATIVA"
        click.echo(
            f"  {camera.id:3d}  {camera.name:24s} {camera.source_type:8s} {estado:8s} "
            f"{redigir_segredos(camera.source)}"
        )


def register_cli(app: Flask) -> None:
    app.cli.add_command(users_cli)
    app.cli.add_command(cameras_cli)
