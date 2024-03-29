"""empty message

Revision ID: 251d7bd3641c
Revises: b2b35103cfec
Create Date: 2022-03-02 01:04:44.614548

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '251d7bd3641c'
down_revision = 'b2b35103cfec'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('teams', sa.Column('vpn2_connected', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('teams', 'vpn2_connected')
    # ### end Alembic commands ###
