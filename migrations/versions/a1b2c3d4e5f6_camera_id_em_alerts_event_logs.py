"""camera_id em alerts e event_logs

Atribui cada alerta/evento à câmera que o gerou. Antes disso o histórico de
todas as câmeras caía num balde só e era impossível dizer de onde veio um
alerta — e o `resolve_all_active` do start de uma câmera derrubava os alertas
vivos de todas as outras.

Nullable de propósito: as linhas que já existem são de antes do multi-câmera e
não têm como ser atribuídas retroativamente. Ficam como NULL = "origem
desconhecida", que a API já trata.

Revision ID: a1b2c3d4e5f6
Revises: f6cd160ae4e0
Create Date: 2026-08-24 09:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f6cd160ae4e0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("camera_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_alerts_camera_id"), ["camera_id"], unique=False)

    with op.batch_alter_table("event_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("camera_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_event_logs_camera_id"), ["camera_id"], unique=False)


def downgrade():
    with op.batch_alter_table("event_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_event_logs_camera_id"))
        batch_op.drop_column("camera_id")

    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alerts_camera_id"))
        batch_op.drop_column("camera_id")
