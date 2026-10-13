"""Добавить версию для конкурентного редактирования черновика.

Revision ID: 6e0a8b43f217
Revises: 4f6b8a21c903
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e0a8b43f217"
down_revision: str | Sequence[str] | None = "4f6b8a21c903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_characters_version_positive", "characters", "version > 0"
    )


def downgrade() -> None:
    bind = op.get_bind()
    changed = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM characters WHERE version <> 1)")
    ).scalar_one()
    if changed:
        raise RuntimeError("Нельзя удалить данные о версиях персонажей")
    op.drop_constraint("ck_characters_version_positive", "characters", type_="check")
    op.drop_column("characters", "version")
