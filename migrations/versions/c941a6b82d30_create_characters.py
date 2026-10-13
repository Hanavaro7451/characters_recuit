"""Create characters linked to campaign memberships.

Revision ID: c941a6b82d30
Revises: 7a35c892e146
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c941a6b82d30"
down_revision: str | Sequence[str] | None = "7a35c892e146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_member_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("race", sa.String(length=255), nullable=False),
        sa.Column("character_class", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PENDING_APPROVAL",
                "ACTIVE",
                "ARCHIVED",
                name="characterstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "archive_reason",
            sa.Enum("CHARACTER_DEAD", "CAMPAIGN_COMPLETED", name="archivereason"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_member_id"], ["campaign_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_member_id", name="uix_character_campaign_member_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("characters")
    sa.Enum(name="archivereason").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="characterstatus").drop(op.get_bind(), checkfirst=True)
