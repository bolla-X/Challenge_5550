"""permissão de trabalho digital e zona controlada (MISSÃO 4, M5)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'permissoes_trabalho',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.String(length=24), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('descricao', sa.String(length=500), nullable=False),
        sa.Column('responsavel', sa.String(length=120), nullable=False),
        sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fim', sa.DateTime(timezone=True), nullable=False),
        sa.Column('epis_exigidos', sa.JSON(), nullable=False),
        sa.Column('exige_vigia', sa.Boolean(), nullable=False),
        sa.Column('area_vigia', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('criada_por', sa.String(length=180), nullable=False),
        sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('encerrada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('encerrada_por', sa.String(length=180), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('permissoes_trabalho', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permissoes_trabalho_numero'), ['numero'], unique=True)
        batch_op.create_index(batch_op.f('ix_permissoes_trabalho_camera_id'), ['camera_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_permissoes_trabalho_tipo'), ['tipo'], unique=False)
        batch_op.create_index(batch_op.f('ix_permissoes_trabalho_fim'), ['fim'], unique=False)
        batch_op.create_index(batch_op.f('ix_permissoes_trabalho_status'), ['status'], unique=False)

    op.create_table(
        'zonas_controladas',
        sa.Column('camera_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('exige_permissao', sa.Boolean(), nullable=False),
        sa.Column('atualizada_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('camera_id'),
    )


def downgrade():
    op.drop_table('zonas_controladas')
    with op.batch_alter_table('permissoes_trabalho', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_permissoes_trabalho_status'))
        batch_op.drop_index(batch_op.f('ix_permissoes_trabalho_fim'))
        batch_op.drop_index(batch_op.f('ix_permissoes_trabalho_tipo'))
        batch_op.drop_index(batch_op.f('ix_permissoes_trabalho_camera_id'))
        batch_op.drop_index(batch_op.f('ix_permissoes_trabalho_numero'))
    op.drop_table('permissoes_trabalho')
