"""planta baixa por camera (G5): calibracao da homografia

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
Create Date: 2026-10-13 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f9a0b1c2d3e4'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('planta', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_column('planta')
