"""record tick information in DB

Revision ID: d2f5aba10faa
Revises: d3f46a7baef6
Create Date: 2024-12-12 23:20:10.845605

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd2f5aba10faa'
down_revision = 'd3f46a7baef6'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ticks',
                    sa.Column('tick', sa.Integer(), nullable=False),
                    sa.Column('start', sa.TIMESTAMP(timezone=True), server_default=sa.text('NULL'), nullable=True),
                    sa.Column('end', sa.TIMESTAMP(timezone=True), server_default=sa.text('NULL'), nullable=True),
                    sa.PrimaryKeyConstraint('tick')
                    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('ticks')
    # ### end Alembic commands ###
