"""empty message

Revision ID: b2b35103cfec
Revises: 55a062b550bf
Create Date: 2021-04-25 19:07:23.139711

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2b35103cfec'
down_revision = '55a062b550bf'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('services', sa.Column('checker_route', sa.String(length=64), server_default=sa.text('NULL'), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('services', 'checker_route')
    # ### end Alembic commands ###
