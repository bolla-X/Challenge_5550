"""regras do editor sem código (MISSÃO 4, M4)

Revision ID: d2e3f4a5b6c7
Revises: c9d0e1f2a3b4
Create Date: 2026-10-17 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd2e3f4a5b6c7'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'regras_editor',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('definicao', sa.JSON(), nullable=False),
        sa.Column('ativa', sa.Boolean(), nullable=False),
        sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizada_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('criada_por', sa.String(length=160), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_regras_editor_ativa'), 'regras_editor', ['ativa'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_regras_editor_ativa'), table_name='regras_editor')
    op.drop_table('regras_editor')
