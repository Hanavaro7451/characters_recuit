from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AbilityRollSet(Base):
    __tablename__ = "ability_roll_sets"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_ability_roll_sets_character"),
        UniqueConstraint(
            "character_id", "id", name="uq_ability_roll_sets_character_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    character: Mapped["Character"] = relationship(
        "Character", back_populates="ability_roll_set"
    )
    results: Mapped[list["AbilityRollResult"]] = relationship(
        "AbilityRollResult",
        back_populates="roll_set",
        order_by="AbilityRollResult.position",
    )


class AbilityRollResult(Base):
    __tablename__ = "ability_roll_results"
    __table_args__ = (
        UniqueConstraint("roll_set_id", "id", name="uq_ability_roll_results_set_id"),
        UniqueConstraint(
            "roll_set_id", "position", name="uq_ability_roll_results_position"
        ),
        CheckConstraint(
            "position BETWEEN 1 AND 6", name="ck_ability_roll_results_position"
        ),
        CheckConstraint(
            "die_one BETWEEN 1 AND 6", name="ck_ability_roll_results_die_one"
        ),
        CheckConstraint(
            "die_two BETWEEN 1 AND 6", name="ck_ability_roll_results_die_two"
        ),
        CheckConstraint(
            "die_three BETWEEN 1 AND 6", name="ck_ability_roll_results_die_three"
        ),
        CheckConstraint(
            "die_four BETWEEN 1 AND 6", name="ck_ability_roll_results_die_four"
        ),
        CheckConstraint(
            "dropped_index BETWEEN 0 AND 3", name="ck_ability_roll_results_dropped"
        ),
        CheckConstraint("total BETWEEN 3 AND 18", name="ck_ability_roll_results_total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roll_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ability_roll_sets.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    die_one: Mapped[int] = mapped_column(Integer, nullable=False)
    die_two: Mapped[int] = mapped_column(Integer, nullable=False)
    die_three: Mapped[int] = mapped_column(Integer, nullable=False)
    die_four: Mapped[int] = mapped_column(Integer, nullable=False)
    dropped_index: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_set: Mapped[AbilityRollSet] = relationship(
        "AbilityRollSet", back_populates="results"
    )

    @property
    def dice(self) -> list[int]:
        return [self.die_one, self.die_two, self.die_three, self.die_four]


if TYPE_CHECKING:
    from app.models.character import Character
