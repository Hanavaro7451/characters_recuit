"""Сохранить распределение результатов и выбор бонусов предыстории.

Revision ID: 9b41a7c6e205
Revises: 8c2e7d4a91b0
"""

from collections.abc import Sequence
from itertools import combinations

import sqlalchemy as sa
from alembic import op

revision: str = "9b41a7c6e205"
down_revision: str | Sequence[str] | None = "8c2e7d4a91b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ability_roll_sets_character_id", "ability_roll_sets", ["character_id", "id"]
    )
    op.create_unique_constraint(
        "uq_ability_roll_results_set_id", "ability_roll_results", ["roll_set_id", "id"]
    )
    op.create_table(
        "ability_distributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False
        ),
        sa.Column(
            "roll_set_id",
            sa.Integer(),
            sa.ForeignKey("ability_roll_sets.id"),
            nullable=False,
        ),
        *(
            sa.Column(f"{ability}_result_id", sa.Integer(), nullable=False)
            for ability in ABILITIES
        ),
        sa.Column("pattern", sa.String(length=32), nullable=True),
        sa.Column("plus_two", sa.String(length=3), nullable=True),
        sa.Column("plus_one", sa.String(length=3), nullable=True),
        sa.UniqueConstraint("character_id", name="uq_ability_distributions_character"),
        sa.UniqueConstraint("roll_set_id", name="uq_ability_distributions_roll_set"),
        sa.ForeignKeyConstraint(
            ["character_id", "roll_set_id"],
            ["ability_roll_sets.character_id", "ability_roll_sets.id"],
            name="fk_ability_distributions_character_roll_set",
        ),
        *(
            sa.ForeignKeyConstraint(
                ["roll_set_id", f"{ability}_result_id"],
                ["ability_roll_results.roll_set_id", "ability_roll_results.id"],
                name=f"fk_ability_distributions_{ability}_result",
            )
            for ability in ABILITIES
        ),
        sa.CheckConstraint(
            " AND ".join(
                f"{first}_result_id <> {second}_result_id"
                for first, second in combinations(ABILITIES, 2)
            ),
            name="ck_ability_distributions_distinct",
        ),
        sa.CheckConstraint(
            "(pattern IS NOT NULL AND pattern = 'plus_one_each' "
            "AND plus_two IS NULL AND plus_one IS NULL) "
            "OR (pattern IS NOT NULL AND pattern = 'plus_two_plus_one' "
            "AND plus_two IS NOT NULL "
            "AND plus_one IS NOT NULL AND plus_two IN "
            "('STR','DEX','CON','INT','WIS','CHA') AND plus_one IN "
            "('STR','DEX','CON','INT','WIS','CHA') AND plus_two <> plus_one) "
            "OR (pattern IS NULL AND plus_two IS NULL AND plus_one IS NULL)",
            name="ck_ability_distributions_choice",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM ability_distributions)")
    ).scalar_one():
        raise RuntimeError("Нельзя удалить сохранённые распределения характеристик")
    op.drop_table("ability_distributions")
    op.drop_constraint(
        "uq_ability_roll_results_set_id", "ability_roll_results", type_="unique"
    )
    op.drop_constraint(
        "uq_ability_roll_sets_character_id", "ability_roll_sets", type_="unique"
    )
