"""the invitation a player registered with (partner links, task 26.2)

Revision ID: d5f8b1c3e7a2
Revises: c4e7a9d2b6f1
Create Date: 2026-11-25 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5f8b1c3e7a2'
down_revision: str | Sequence[str] | None = 'c4e7a9d2b6f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('invite_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_users_invite_id'), 'users', ['invite_id'], unique=False)
    op.create_foreign_key('users_invite_id_fkey', 'users', 'invites', ['invite_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('users_invite_id_fkey', 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_invite_id'), table_name='users')
    op.drop_column('users', 'invite_id')
