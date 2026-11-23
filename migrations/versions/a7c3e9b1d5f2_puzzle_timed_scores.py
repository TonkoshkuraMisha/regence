"""puzzle timed scores

Weekly scores of timed runs (leaderboard, task 26.1): a player's best score for the week by run length.

Revision ID: a7c3e9b1d5f2
Revises: e4b9c2d7a1f3
Create Date: 2026-11-22 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e9b1d5f2'
down_revision: str | Sequence[str] | None = 'e4b9c2d7a1f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'puzzle_timed_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'minutes', 'week', name='uq_puzzle_timed_scores_week'),
    )
    op.create_index(op.f('ix_puzzle_timed_scores_user_id'), 'puzzle_timed_scores', ['user_id'], unique=False)
    op.create_index(op.f('ix_puzzle_timed_scores_week'), 'puzzle_timed_scores', ['week'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_puzzle_timed_scores_week'), table_name='puzzle_timed_scores')
    op.drop_index(op.f('ix_puzzle_timed_scores_user_id'), table_name='puzzle_timed_scores')
    op.drop_table('puzzle_timed_scores')
