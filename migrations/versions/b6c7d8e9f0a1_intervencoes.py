"""intervencoes para o antes/depois e o ROI (MISSÃO 4, M8)

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-17 20:00:00.000000

Uma tabela nova; nenhuma tabela existente muda. Sem backfill: nasce vazia.
Rollback: `downgrade` apaga a tabela (só perde as intervenções cadastradas).
"""
from alembic import op
import sqlalchemy as sa


revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'intervencoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('setor', sa.String(length=160), nullable=True),
        sa.Column('titulo', sa.String(length=160), nullable=False),
        sa.Column('descricao', sa.String(length=2000), nullable=False),
        sa.Column('data_da_intervencao', sa.Date(), nullable=False),
        sa.Column('criada_por', sa.String(length=180), nullable=False),
        sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('intervencoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_intervencoes_camera_id'), ['camera_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_intervencoes_data_da_intervencao'), ['data_da_intervencao'], unique=False)
        batch_op.create_index(batch_op.f('ix_intervencoes_setor'), ['setor'], unique=False)


def downgrade():
    with op.batch_alter_table('intervencoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_intervencoes_setor'))
        batch_op.drop_index(batch_op.f('ix_intervencoes_data_da_intervencao'))
        batch_op.drop_index(batch_op.f('ix_intervencoes_camera_id'))
    op.drop_table('intervencoes')
