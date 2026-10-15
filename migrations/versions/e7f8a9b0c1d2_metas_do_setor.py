"""metas do setor (Modo TV, G8)

Revision ID: e7f8a9b0c1d2
Revises: d1e2f3a4b5c6
Create Date: 2026-10-13 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e7f8a9b0c1d2'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'metas_setor',
        sa.Column('setor', sa.String(length=160), nullable=False),
        sa.Column('minutos_conformes', sa.Integer(), nullable=True),
        sa.Column('checkins_portal', sa.Integer(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('setor'),
    )


def downgrade():
    op.drop_table('metas_setor')
