"""add timezone info

Revision ID: 4225a3d6edbd
Revises: ddd894b2c20c

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4225a3d6edbd'
down_revision = 'ddd894b2c20c'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('checker_results', 'finished', type_=sa.TIMESTAMP(timezone=True))
    op.alter_column('logmessages', 'created', type_=sa.TIMESTAMP(timezone=True))
    op.alter_column('submitted_flags', 'ts', type_=sa.TIMESTAMP(timezone=True))
    op.alter_column('teams', 'vpn_last_connect', type_=sa.TIMESTAMP(timezone=True))
    op.alter_column('teams', 'vpn_last_disconnect', type_=sa.TIMESTAMP(timezone=True))
    op.alter_column('team_traffic_stats', 'time', type_=sa.TIMESTAMP(timezone=True))
    pass


def downgrade():
    pass
