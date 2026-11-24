"""weekly tournament against legends

Revision ID: d6a1f3c8e2b9
Revises: c4e7a9d2b6f1
Create Date: 2026-11-24 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd6a1f3c8e2b9'
down_revision: str | Sequence[str] | None = 'c4e7a9d2b6f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'weekly_legend_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(length=32), nullable=False),
        sa.Column('half_points', sa.Integer(), nullable=False),
        sa.Column('forfeit', sa.String(length=32), nullable=True),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('week', 'user_id', 'bot_id', name='uq_weekly_legend_games_week_user_bot'),
    )
    op.create_index(op.f('ix_weekly_legend_games_week'), 'weekly_legend_games', ['week'], unique=False)
    op.create_index(op.f('ix_weekly_legend_games_user_id'), 'weekly_legend_games', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_weekly_legend_games_user_id'), table_name='weekly_legend_games')
    op.drop_index(op.f('ix_weekly_legend_games_week'), table_name='weekly_legend_games')
    op.drop_table('weekly_legend_games')
