"""liga de setores e missões da equipe (X8, MISSÃO 2)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-14 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'liga_pontos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setor', sa.String(length=160), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('pontos', sa.Integer(), nullable=False),
        sa.Column('ref', sa.String(length=120), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tipo', 'ref', name='uq_liga_tipo_ref'),
    )
    for coluna in ('setor', 'tipo', 'criado_em'):
        op.create_index(f'ix_liga_pontos_{coluna}', 'liga_pontos', [coluna])
    op.create_table(
        'missoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=160), nullable=False),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('alvo', sa.Integer(), nullable=False),
        sa.Column('ate_hora', sa.String(length=5), nullable=True),
        sa.Column('setor', sa.String(length=160), nullable=True),
        sa.Column('ativa', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('missoes')
    op.drop_table('liga_pontos')
