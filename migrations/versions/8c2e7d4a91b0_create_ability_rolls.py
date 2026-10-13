"""Добавить неизменяемые наборы бросков характеристик.

Revision ID: 8c2e7d4a91b0
Revises: 6e0a8b43f217
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c2e7d4a91b0"
down_revision: str | Sequence[str] | None = "6e0a8b43f217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ability_roll_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("character_id", name="uq_ability_roll_sets_character"),
    )
    op.create_table(
        "ability_roll_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "roll_set_id",
            sa.Integer(),
            sa.ForeignKey("ability_roll_sets.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("die_one", sa.Integer(), nullable=False),
        sa.Column("die_two", sa.Integer(), nullable=False),
        sa.Column("die_three", sa.Integer(), nullable=False),
        sa.Column("die_four", sa.Integer(), nullable=False),
        sa.Column("dropped_index", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "roll_set_id", "position", name="uq_ability_roll_results_position"
        ),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 6", name="ck_ability_roll_results_position"
        ),
        sa.CheckConstraint(
            "die_one BETWEEN 1 AND 6", name="ck_ability_roll_results_die_one"
        ),
        sa.CheckConstraint(
            "die_two BETWEEN 1 AND 6", name="ck_ability_roll_results_die_two"
        ),
        sa.CheckConstraint(
            "die_three BETWEEN 1 AND 6", name="ck_ability_roll_results_die_three"
        ),
        sa.CheckConstraint(
            "die_four BETWEEN 1 AND 6", name="ck_ability_roll_results_die_four"
        ),
        sa.CheckConstraint(
            "dropped_index BETWEEN 0 AND 3", name="ck_ability_roll_results_dropped"
        ),
        sa.CheckConstraint(
            "total BETWEEN 3 AND 18", name="ck_ability_roll_results_total"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_data = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM ability_roll_sets)")
    ).scalar_one()
    if has_data:
        raise RuntimeError("Нельзя удалить сохранённые наборы бросков")
    op.drop_table("ability_roll_results")
    op.drop_table("ability_roll_sets")
