from itertools import combinations
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AbilityDistribution(Base):
    __tablename__ = "ability_distributions"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_ability_distributions_character"),
        UniqueConstraint("roll_set_id", name="uq_ability_distributions_roll_set"),
        ForeignKeyConstraint(
            ["character_id", "roll_set_id"],
            ["ability_roll_sets.character_id", "ability_roll_sets.id"],
            name="fk_ability_distributions_character_roll_set",
        ),
        *(
            ForeignKeyConstraint(
                ["roll_set_id", f"{ability.lower()}_result_id"],
                ["ability_roll_results.roll_set_id", "ability_roll_results.id"],
                name=f"fk_ability_distributions_{ability.lower()}_result",
            )
            for ability in ("STR", "DEX", "CON", "INT", "WIS", "CHA")
        ),
        CheckConstraint(
            " AND ".join(
                f"{first}_result_id <> {second}_result_id"
                for first, second in combinations(
                    ("str", "dex", "con", "int", "wis", "cha"), 2
                )
            ),
            name="ck_ability_distributions_distinct",
        ),
        CheckConstraint(
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id"), nullable=False
    )
    roll_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ability_roll_sets.id"), nullable=False
    )
    str_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dex_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    con_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    int_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    wis_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cha_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plus_two: Mapped[str | None] = mapped_column(String(3), nullable=True)
    plus_one: Mapped[str | None] = mapped_column(String(3), nullable=True)
    character: Mapped["Character"] = relationship(
        "Character", back_populates="ability_distribution"
    )


if TYPE_CHECKING:
    from app.models.character import Character
