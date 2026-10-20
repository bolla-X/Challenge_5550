"""missoes.desativada_em: quando o supervisor apagou a missão (MISSÃO 4, PR10)

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-10-19 15:00:00.000000

Uma coluna nova, anulável, sem default: as linhas existentes ficam com NULL.
Missão já apagada antes desta migração (ativa = false, desativada_em NULL) não
tem a data e continua fora da retrospectiva, como antes. Sem backfill.
Rollback: `downgrade` remove a coluna (só perde a data de exclusão).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('missoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('desativada_em', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('missoes', schema=None) as batch_op:
        batch_op.drop_column('desativada_em')
