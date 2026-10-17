"""feedback dentro do app e contatos da página pública /produto (MISSÃO 4, Fase 3)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-17 18:00:00.000000

Duas tabelas novas e independentes; nenhuma tabela existente muda. Sem backfill:
nascem vazias. Rollback: `downgrade` apaga as duas (só perde o que foi escrito nelas).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(length=2000), nullable=False),
        sa.Column('tela', sa.String(length=200), nullable=True),
        sa.Column('tipo_de_conta', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lido', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_criado_em'), ['criado_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_lido'), ['lido'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_user_id'), ['user_id'], unique=False)

    op.create_table(
        'contatos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('empresa', sa.String(length=160), nullable=True),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('mensagem', sa.String(length=2000), nullable=False),
        sa.Column('consentimento', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lido', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('contatos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contatos_criado_em'), ['criado_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_contatos_lido'), ['lido'], unique=False)


def downgrade():
    with op.batch_alter_table('contatos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contatos_lido'))
        batch_op.drop_index(batch_op.f('ix_contatos_criado_em'))
    op.drop_table('contatos')

    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feedback_user_id'))
        batch_op.drop_index(batch_op.f('ix_feedback_lido'))
        batch_op.drop_index(batch_op.f('ix_feedback_criado_em'))
    op.drop_table('feedback')
