"""Allow campaigns without an active invite code.

Revision ID: 7a35c892e146
Revises: eec067041dd7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a35c892e146"
down_revision: str | Sequence[str] | None = "eec067041dd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "campaigns", "invite_code", existing_type=sa.String(length=255), nullable=True
    )


def downgrade() -> None:
    # PostgreSQL rejects this change if revoked (NULL) codes still exist.
    # Do not silently reactivate invitations or delete campaigns to allow rollback.
    op.alter_column(
        "campaigns", "invite_code", existing_type=sa.String(length=255), nullable=False
    )
