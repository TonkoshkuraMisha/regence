"""import subscriptions

Revision ID: f7b3d9e1a5c2
Revises: e6a9c2f4b8d1
Create Date: 2026-11-28 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7b3d9e1a5c2'
down_revision: str | Sequence[str] | None = 'e6a9c2f4b8d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('import_subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('username', sa.String(length=30), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_added', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_error', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('lichess', 'chesscom')", name='ck_import_subscriptions_source'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'source', name='uq_import_subscriptions_source')
    )
    op.create_index(op.f('ix_import_subscriptions_last_run_at'), 'import_subscriptions', ['last_run_at'], unique=False)
    op.create_index(op.f('ix_import_subscriptions_user_id'), 'import_subscriptions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_import_subscriptions_user_id'), table_name='import_subscriptions')
    op.drop_index(op.f('ix_import_subscriptions_last_run_at'), table_name='import_subscriptions')
    op.drop_table('import_subscriptions')
