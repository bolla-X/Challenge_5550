"""modo portaria: EPIs obrigatorios por camera

Revision ID: d1e2f3a4b5c6
Revises: cd57c8841519
Create Date: 2026-09-20 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'cd57c8841519'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gate_required', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_column('gate_required')
