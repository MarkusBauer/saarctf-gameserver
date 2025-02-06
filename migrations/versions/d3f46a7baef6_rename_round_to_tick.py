"""rename round to tick

Revision ID: d3f46a7baef6
Revises: 922cc6992093
Create Date: 2024-12-12 21:27:08.687162

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd3f46a7baef6'
down_revision = '922cc6992093'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('checker_results', 'round', nullable=False, new_column_name='tick')
    op.drop_index('ix_checker_results_round', table_name='checker_results')
    op.create_index(op.f('ix_checker_results_tick'), 'checker_results', ['tick'], unique=False)

    op.alter_column('services', 'flags_per_round', nullable=False, new_column_name='flags_per_tick')

    op.alter_column('submitted_flags', 'round_submitted', nullable=False, new_column_name='tick_submitted')
    op.alter_column('submitted_flags', 'round_issued', nullable=False, new_column_name='tick_issued')
    op.drop_index('ix_submitted_flags_round_submitted', table_name='submitted_flags')
    op.create_index(op.f('ix_submitted_flags_tick_submitted'), 'submitted_flags', ['tick_submitted'], unique=False)

    op.alter_column('team_points', 'round', nullable=False, new_column_name='tick')
    op.drop_index('ix_team_points_round', table_name='team_points')
    op.create_index(op.f('ix_team_points_tick'), 'team_points', ['tick'], unique=False)

    op.alter_column('team_rankings', 'round', nullable=False, new_column_name='tick')
    op.drop_index('ix_team_rankings_round', table_name='team_rankings')
    op.create_index(op.f('ix_team_rankings_tick'), 'team_rankings', ['tick'], unique=False)


def downgrade():
    op.alter_column('checker_results', 'tick', nullable=False, new_column_name='round')
    op.drop_index(op.f('ix_checker_results_tick'), table_name='checker_results')
    op.create_index('ix_checker_results_round', 'checker_results', ['round'], unique=False)

    op.alter_column('services', 'flags_per_tick', nullable=False, new_column_name='flags_per_round')

    op.alter_column('submitted_flags', 'tick_submitted', nullable=False, new_column_name='round_submitted')
    op.alter_column('submitted_flags', 'tick_issued', nullable=False, new_column_name='round_issued')
    op.drop_index(op.f('ix_submitted_flags_tick_submitted'), table_name='submitted_flags')
    op.create_index('ix_submitted_flags_round_submitted', 'submitted_flags', ['round_submitted'], unique=False)

    op.alter_column('team_points', 'tick', nullable=False, new_column_name='round')
    op.drop_index(op.f('ix_team_points_tick'), table_name='team_points')
    op.create_index('ix_team_points_round', 'team_points', ['round'], unique=False)

    op.alter_column('team_rankings', 'tick', nullable=False, new_column_name='round')
    op.drop_index(op.f('ix_team_rankings_tick'), table_name='team_rankings')
    op.create_index('ix_team_rankings_round', 'team_rankings', ['round'], unique=False)
