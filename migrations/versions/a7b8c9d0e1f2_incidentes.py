"""incidentes (alertas agrupados por câmera, regra e zona — MISSÃO 2, P0.2)

Revision ID: a7b8c9d0e1f2
Revises: f9a0b1c2d3e4
Create Date: 2026-10-14 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'incidentes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('rule', sa.String(length=80), nullable=False),
        sa.Column('feature', sa.String(length=80), nullable=True),
        sa.Column('zona', sa.String(length=120), nullable=False),
        sa.Column('severity', sa.String(length=30), nullable=False),
        sa.Column('titulo', sa.String(length=160), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('pessoas', sa.JSON(), nullable=False),
        sa.Column('alert_ids', sa.JSON(), nullable=False),
        sa.Column('pico_pessoas', sa.Integer(), nullable=False),
        sa.Column('aberto_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fechado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reconhecido_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reconhecido_papel', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    for coluna in ('camera_id', 'rule', 'feature', 'severity', 'status', 'aberto_em', 'fechado_em'):
        op.create_index(f'ix_incidentes_{coluna}', 'incidentes', [coluna])


def downgrade():
    op.drop_table('incidentes')
