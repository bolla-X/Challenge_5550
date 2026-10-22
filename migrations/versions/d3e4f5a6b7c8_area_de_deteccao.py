"""area de deteccao por camera (MISSAO 7): onde o sistema procura pessoas

Revision ID: d3e4f5a6b7c8
Revises: c7d8e9f0a1b2
Create Date: 2026-10-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e4f5a6b7c8'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    # Nula = quadro inteiro: as cameras que ja existem continuam exatamente como estavam.
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('area_deteccao', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_column('area_deteccao')
