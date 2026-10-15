"""cadeia de custódia das evidências (X3, MISSÃO 2)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-14 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custodia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('ref', sa.String(length=240), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('descricao', sa.String(length=255), nullable=False),
        sa.Column('detalhe', sa.JSON(), nullable=False),
        sa.Column('conteudo_sha256', sa.String(length=64), nullable=False),
        sa.Column('anterior_sha256', sa.String(length=64), nullable=False),
        sa.Column('elo_sha256', sa.String(length=64), nullable=False),
        sa.Column('criado_em', sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('elo_sha256'),
    )
    for coluna in ('tipo', 'camera_id', 'alert_id'):
        op.create_index(f'ix_custodia_{coluna}', 'custodia', [coluna])


def downgrade():
    op.drop_table('custodia')
