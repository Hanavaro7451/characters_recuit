from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CatalogEntry:
    """Catalog version; DB trigger protects all fields except selection availability."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    ruleset: Mapped[str] = mapped_column(
        String(50), nullable=False, default="dnd-2024", server_default="dnd-2024"
    )
    content_version: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    license_name: Mapped[str] = mapped_column(String(255), nullable=False)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    available_for_selection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class SpeciesCatalog(CatalogEntry, Base):
    __tablename__ = "species_catalog"
    __table_args__ = (
        UniqueConstraint(
            "ruleset", "code", "content_version", name="uq_species_version"
        ),
    )


class ClassCatalog(CatalogEntry, Base):
    __tablename__ = "class_catalog"
    __table_args__ = (
        UniqueConstraint("ruleset", "code", "content_version", name="uq_class_version"),
    )


class BackgroundCatalog(CatalogEntry, Base):
    __tablename__ = "background_catalog"
    __table_args__ = (
        UniqueConstraint(
            "ruleset", "code", "content_version", name="uq_background_version"
        ),
        CheckConstraint(
            "ability_one IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA') "
            "AND ability_two IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA') "
            "AND ability_three IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA')",
            name="ck_background_abilities_valid",
        ),
        CheckConstraint(
            "ability_one <> ability_two AND ability_one <> ability_three "
            "AND ability_two <> ability_three",
            name="ck_background_abilities_distinct",
        ),
        CheckConstraint(
            "allow_plus_two_plus_one OR allow_plus_one_each",
            name="ck_background_bonus_pattern",
        ),
    )

    ability_one: Mapped[str] = mapped_column(String(3), nullable=False)
    ability_two: Mapped[str] = mapped_column(String(3), nullable=False)
    ability_three: Mapped[str] = mapped_column(String(3), nullable=False)
    allow_plus_two_plus_one: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_plus_one_each: Mapped[bool] = mapped_column(Boolean, nullable=False)
