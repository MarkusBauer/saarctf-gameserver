"""empty message

Revision ID: 6a3f046884d6
Revises: 251d7bd3641c
Create Date: 2022-05-19 11:26:41.939234

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6a3f046884d6'
down_revision = '251d7bd3641c'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('services', 'flags_per_round', existing_type=sa.Integer(), type_=sa.Float())


def downgrade():
    op.alter_column('services', 'flags_per_round', existing_type=sa.Float(), type_=sa.Integer())
