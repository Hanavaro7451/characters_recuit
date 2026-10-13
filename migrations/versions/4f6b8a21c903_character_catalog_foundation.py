"""Добавить версионированные справочники и переходные ссылки персонажа.

Revision ID: 4f6b8a21c903
Revises: d85fb6214e09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f6b8a21c903"
down_revision: str | Sequence[str] | None = "d85fb6214e09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _catalog_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("ruleset", sa.String(50), server_default="dnd-2024", nullable=False),
        sa.Column("content_version", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_title", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("license_name", sa.String(255), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column(
            "available_for_selection",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    columns = {
        column["name"]: column
        for column in sa.inspect(op.get_bind()).get_columns("characters")
    }
    op.create_table(
        "catalog_schema_upgrade_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("race_existed", sa.Boolean(), nullable=False),
        sa.Column("race_was_nullable", sa.Boolean(), nullable=True),
        sa.Column("class_existed", sa.Boolean(), nullable=False),
        sa.Column("class_was_nullable", sa.Boolean(), nullable=True),
    )
    state = sa.table(
        "catalog_schema_upgrade_state",
        sa.column("id", sa.Integer()),
        sa.column("race_existed", sa.Boolean()),
        sa.column("race_was_nullable", sa.Boolean()),
        sa.column("class_existed", sa.Boolean()),
        sa.column("class_was_nullable", sa.Boolean()),
    )
    op.bulk_insert(
        state,
        [
            {
                "id": 1,
                "race_existed": "race" in columns,
                "race_was_nullable": columns["race"]["nullable"]
                if "race" in columns
                else None,
                "class_existed": "character_class" in columns,
                "class_was_nullable": columns["character_class"]["nullable"]
                if "character_class" in columns
                else None,
            }
        ],
    )
    for table, constraint in (
        ("species_catalog", "uq_species_version"),
        ("class_catalog", "uq_class_version"),
    ):
        op.create_table(
            table,
            *_catalog_columns(),
            sa.UniqueConstraint("ruleset", "code", "content_version", name=constraint),
        )
    op.create_table(
        "background_catalog",
        *_catalog_columns(),
        sa.Column("ability_one", sa.String(3), nullable=False),
        sa.Column("ability_two", sa.String(3), nullable=False),
        sa.Column("ability_three", sa.String(3), nullable=False),
        sa.Column("allow_plus_two_plus_one", sa.Boolean(), nullable=False),
        sa.Column("allow_plus_one_each", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "ability_one IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA') "
            "AND ability_two IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA') "
            "AND ability_three IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA')",
            name="ck_background_abilities_valid",
        ),
        sa.CheckConstraint(
            "ability_one <> ability_two AND ability_one <> ability_three "
            "AND ability_two <> ability_three",
            name="ck_background_abilities_distinct",
        ),
        sa.CheckConstraint(
            "allow_plus_two_plus_one OR allow_plus_one_each",
            name="ck_background_bonus_pattern",
        ),
        sa.UniqueConstraint(
            "ruleset", "code", "content_version", name="uq_background_version"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION protect_catalog_version() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Published catalog versions cannot be deleted';
            END IF;
            IF (to_jsonb(NEW) - 'available_for_selection') IS DISTINCT FROM
               (to_jsonb(OLD) - 'available_for_selection') THEN
                RAISE EXCEPTION 'Published catalog versions cannot be changed';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("species_catalog", "class_catalog", "background_catalog"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_catalog_version()"
        )
    for column in ("race", "character_class"):
        if column in columns:
            op.alter_column(
                "characters",
                column,
                existing_type=columns[column]["type"],
                nullable=True,
            )
        else:
            op.add_column(
                "characters", sa.Column(column, sa.String(255), nullable=True)
            )
    for column, table in (
        ("species_id", "species_catalog"),
        ("class_catalog_id", "class_catalog"),
        ("background_id", "background_catalog"),
    ):
        op.add_column("characters", sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_characters_{column}", "characters", table, [column], ["id"]
        )
        op.create_index(f"ix_characters_{column}", "characters", [column])
    op.add_column(
        "characters",
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_characters_level_positive", "characters", "level > 0"
    )


def downgrade() -> None:
    bind = op.get_bind()
    state = bind.execute(
        sa.text(
            "SELECT race_existed, race_was_nullable, class_existed, "
            "class_was_nullable FROM catalog_schema_upgrade_state WHERE id = 1"
        )
    ).one()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM species_catalog) "
            "OR EXISTS (SELECT 1 FROM class_catalog) "
            "OR EXISTS (SELECT 1 FROM background_catalog) "
            "OR EXISTS (SELECT 1 FROM characters WHERE "
            "species_id IS NOT NULL OR class_catalog_id IS NOT NULL "
            "OR background_id IS NOT NULL OR level <> 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("Откат уничтожит справочные данные или ссылки персонажа")
    for column, existed, was_nullable in (
        ("race", state.race_existed, state.race_was_nullable),
        ("character_class", state.class_existed, state.class_was_nullable),
    ):
        if existed and not was_nullable:
            invalid = bind.execute(
                sa.text(
                    f"SELECT EXISTS (SELECT 1 FROM characters WHERE {column} IS NULL)"
                )
            ).scalar_one()
        elif not existed:
            invalid = bind.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM characters WHERE "
                    f"{column} IS NOT NULL)"
                )
            ).scalar_one()
        else:
            invalid = False
        if invalid:
            raise RuntimeError(f"Откат уничтожит или нарушит значения {column}")
    op.drop_constraint("ck_characters_level_positive", "characters", type_="check")
    op.drop_column("characters", "level")
    for column in ("background_id", "class_catalog_id", "species_id"):
        op.drop_index(f"ix_characters_{column}", table_name="characters")
        op.drop_constraint(f"fk_characters_{column}", "characters", type_="foreignkey")
        op.drop_column("characters", column)
    for column, existed, was_nullable in (
        ("race", state.race_existed, state.race_was_nullable),
        ("character_class", state.class_existed, state.class_was_nullable),
    ):
        if existed:
            op.alter_column(
                "characters",
                column,
                existing_type=sa.String(255),
                nullable=was_nullable,
            )
        else:
            op.drop_column("characters", column)
    op.drop_table("background_catalog")
    op.drop_table("class_catalog")
    op.drop_table("species_catalog")
    op.execute("DROP FUNCTION protect_catalog_version()")
    op.drop_table("catalog_schema_upgrade_state")
