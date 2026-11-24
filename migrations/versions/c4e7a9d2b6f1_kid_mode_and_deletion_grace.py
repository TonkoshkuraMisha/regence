"""kid mode and account deletion grace period

Revision ID: c4e7a9d2b6f1
Revises: b8d2f4a6c1e3
Create Date: 2026-11-24 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e7a9d2b6f1'
down_revision: str | Sequence[str] | None = 'b8d2f4a6c1e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_users_deletion_requested_at'), 'users', ['deletion_requested_at'], unique=False)
    op.add_column('users', sa.Column('kid_mode', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('kid_guardian_hash', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'kid_guardian_hash')
    op.drop_column('users', 'kid_mode')
    op.drop_index(op.f('ix_users_deletion_requested_at'), table_name='users')
    op.drop_column('users', 'deletion_requested_at')
