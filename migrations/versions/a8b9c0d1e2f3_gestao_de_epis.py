"""gestao de EPIs: colaboradores, catalogo com CA, entregas e ocorrencias (ES Sprint 4)

Revision ID: a8b9c0d1e2f3
Revises: d3e4f5a6b7c8
Create Date: 2026-10-23 09:00:00.000000

Quatro tabelas novas; nenhuma tabela existente muda. Sem backfill: nascem vazias
(`flask --app wsgi gestao semear` carrega os dados simulados quando alguem quiser).
Rollback: `downgrade` apaga as quatro tabelas (so perde o que foi cadastrado nelas).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'colaboradores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('matricula', sa.String(length=32), nullable=False),
        sa.Column('nome', sa.String(length=160), nullable=False),
        sa.Column('setor', sa.String(length=120), nullable=False),
        sa.Column('funcao', sa.String(length=120), nullable=False),
        sa.Column('admissao', sa.Date(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('ficticio', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('colaboradores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_colaboradores_matricula'), ['matricula'], unique=True)
        batch_op.create_index(batch_op.f('ix_colaboradores_setor'), ['setor'], unique=False)
        batch_op.create_index(batch_op.f('ix_colaboradores_ativo'), ['ativo'], unique=False)

    op.create_table(
        'epis_catalogo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=160), nullable=False),
        sa.Column('categoria', sa.String(length=30), nullable=False),
        sa.Column('ca', sa.String(length=20), nullable=False),
        sa.Column('validade_ca', sa.Date(), nullable=False),
        sa.Column('fabricante', sa.String(length=160), nullable=False),
        sa.Column('vida_util_dias', sa.Integer(), nullable=False),
        sa.Column('ficticio', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('epis_catalogo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_epis_catalogo_categoria'), ['categoria'], unique=False)
        batch_op.create_index(batch_op.f('ix_epis_catalogo_ca'), ['ca'], unique=True)
        batch_op.create_index(batch_op.f('ix_epis_catalogo_validade_ca'), ['validade_ca'], unique=False)

    op.create_table(
        'entregas_epi',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=32), nullable=False),
        sa.Column('colaborador_id', sa.Integer(), nullable=False),
        sa.Column('epi_id', sa.Integer(), nullable=False),
        sa.Column('ca_na_entrega', sa.String(length=20), nullable=False),
        sa.Column('epi_nome_na_entrega', sa.String(length=160), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('entregue_em', sa.Date(), nullable=False),
        sa.Column('troca_prevista_em', sa.Date(), nullable=False),
        sa.Column('devolvido_em', sa.Date(), nullable=True),
        sa.Column('motivo', sa.String(length=20), nullable=False),
        sa.Column('observacao', sa.String(length=500), nullable=False),
        sa.Column('registrado_por', sa.String(length=180), nullable=False),
        sa.Column('ficticio', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['colaborador_id'], ['colaboradores.id']),
        sa.ForeignKeyConstraint(['epi_id'], ['epis_catalogo.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('entregas_epi', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_entregas_epi_codigo'), ['codigo'], unique=True)
        batch_op.create_index(batch_op.f('ix_entregas_epi_colaborador_id'), ['colaborador_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_entregas_epi_epi_id'), ['epi_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_entregas_epi_entregue_em'), ['entregue_em'], unique=False)

    op.create_table(
        'ocorrencias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=32), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('gravidade', sa.String(length=20), nullable=False),
        sa.Column('setor', sa.String(length=160), nullable=False),
        sa.Column('descricao', sa.String(length=2000), nullable=False),
        sa.Column('ocorrida_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('colaborador_id', sa.Integer(), nullable=True),
        sa.Column('acao_corretiva', sa.String(length=2000), nullable=False),
        sa.Column('alerta_id', sa.Integer(), nullable=True),
        sa.Column('registrada_por', sa.String(length=180), nullable=False),
        sa.Column('encerrada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ficticio', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['colaborador_id'], ['colaboradores.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ocorrencias', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ocorrencias_codigo'), ['codigo'], unique=True)
        batch_op.create_index(batch_op.f('ix_ocorrencias_tipo'), ['tipo'], unique=False)
        batch_op.create_index(batch_op.f('ix_ocorrencias_setor'), ['setor'], unique=False)
        batch_op.create_index(batch_op.f('ix_ocorrencias_ocorrida_em'), ['ocorrida_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_ocorrencias_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ocorrencias_colaborador_id'), ['colaborador_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ocorrencias', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ocorrencias_colaborador_id'))
        batch_op.drop_index(batch_op.f('ix_ocorrencias_status'))
        batch_op.drop_index(batch_op.f('ix_ocorrencias_ocorrida_em'))
        batch_op.drop_index(batch_op.f('ix_ocorrencias_setor'))
        batch_op.drop_index(batch_op.f('ix_ocorrencias_tipo'))
        batch_op.drop_index(batch_op.f('ix_ocorrencias_codigo'))
    op.drop_table('ocorrencias')

    with op.batch_alter_table('entregas_epi', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entregas_epi_entregue_em'))
        batch_op.drop_index(batch_op.f('ix_entregas_epi_epi_id'))
        batch_op.drop_index(batch_op.f('ix_entregas_epi_colaborador_id'))
        batch_op.drop_index(batch_op.f('ix_entregas_epi_codigo'))
    op.drop_table('entregas_epi')

    with op.batch_alter_table('epis_catalogo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_epis_catalogo_validade_ca'))
        batch_op.drop_index(batch_op.f('ix_epis_catalogo_ca'))
        batch_op.drop_index(batch_op.f('ix_epis_catalogo_categoria'))
    op.drop_table('epis_catalogo')

    with op.batch_alter_table('colaboradores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_colaboradores_ativo'))
        batch_op.drop_index(batch_op.f('ix_colaboradores_setor'))
        batch_op.drop_index(batch_op.f('ix_colaboradores_matricula'))
    op.drop_table('colaboradores')
