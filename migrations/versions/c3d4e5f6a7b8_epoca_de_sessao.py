"""epoca de sessao em users

Sessao do Flask e cookie ASSINADO, sem estado no servidor: quem copiasse o
cookie continuava autenticado mesmo depois de a senha ser trocada ou a conta
desativada. Isso contradizia o que o README prometia.

`session_epoch` fecha o buraco: a sessao carrega a epoca vigente no login e
`current_user` compara. Incrementar invalida todo cookie ja emitido.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-24 18:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        # server_default garante valor nas linhas que ja existem; o modelo usa
        # default=1 do lado do Python pras novas.
        batch_op.add_column(sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("session_epoch")
