"""primeiro acesso do supervisor: estado do onboarding (MISSÃO 4, Fase 3)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-17 15:00:00.000000

Tabela nova e independente (linha única, id = 1); nenhuma tabela existente muda.
Sem backfill: sem linha, o serviço lê "tudo pendente" e a detecção automática
mostra o que o banco já tem.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'onboarding',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('passos', sa.JSON(), nullable=False),
        sa.Column('concluido_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizado_por', sa.String(length=180), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('onboarding')
