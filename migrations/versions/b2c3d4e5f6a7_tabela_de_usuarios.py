"""tabela de usuarios (autenticacao real)

Pessoas reais com login, senha (hash scrypt) e papel. Ate aqui o sistema nao
tinha autenticacao: qualquer um que alcancasse a porta iniciava/parava camera e
marcava alerta como falso positivo.

`camera_id` e a camera "do setor" do operador — substitui o seletor "simular
setor" que existia na topbar enquanto nao havia login.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-24 17:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_active"), ["active"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_camera_id"), ["camera_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_created_at"), ["created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_created_at"))
        batch_op.drop_index(batch_op.f("ix_users_camera_id"))
        batch_op.drop_index(batch_op.f("ix_users_active"))
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_index(batch_op.f("ix_users_email"))
    op.drop_table("users")
