"""empty message

Revision ID: 55a062b550bf
Revises: 28250d12516f
Create Date: 2021-04-24 00:44:49.502457

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '55a062b550bf'
down_revision = '28250d12516f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('team_traffic_stats', sa.Column('forward_self_bytes', sa.BigInteger(), nullable=False))
    op.add_column('team_traffic_stats', sa.Column('forward_self_packets', sa.BigInteger(), nullable=False))
    op.add_column('team_traffic_stats', sa.Column('forward_self_syn_acks', sa.BigInteger(), nullable=False))
    op.add_column('team_traffic_stats', sa.Column('forward_self_syns', sa.BigInteger(), nullable=False))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('team_traffic_stats', 'forward_self_syns')
    op.drop_column('team_traffic_stats', 'forward_self_syn_acks')
    op.drop_column('team_traffic_stats', 'forward_self_packets')
    op.drop_column('team_traffic_stats', 'forward_self_bytes')
    # ### end Alembic commands ###
