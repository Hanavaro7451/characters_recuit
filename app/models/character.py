from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ArchiveReason, CharacterStatus
from app.models.base import Base, TimestampMixin


class Character(Base, TimestampMixin):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("campaign_member_id", name="uix_character_campaign_member_id"),
        CheckConstraint("level > 0", name="ck_characters_level_positive"),
        CheckConstraint("version > 0", name="ck_characters_version_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign_members.id")
    )
    campaign_member: Mapped["CampaignMember"] = relationship(
        "CampaignMember", back_populates="character"
    )
    status: Mapped[CharacterStatus] = mapped_column(
        Enum(CharacterStatus), default=CharacterStatus.DRAFT
    )
    archive_reason: Mapped[ArchiveReason | None] = mapped_column(
        Enum(ArchiveReason), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Старые текстовые значения сохраняются до однозначного сопоставления версий.
    race: Mapped[str | None] = mapped_column(String(255), nullable=True)
    character_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    species_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("species_catalog.id"), nullable=True, index=True
    )
    class_catalog_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("class_catalog.id"), nullable=True, index=True
    )
    background_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("background_catalog.id"), nullable=True, index=True
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    species: Mapped["SpeciesCatalog | None"] = relationship("SpeciesCatalog")
    class_catalog: Mapped["ClassCatalog | None"] = relationship("ClassCatalog")
    background: Mapped["BackgroundCatalog | None"] = relationship("BackgroundCatalog")
    ability_roll_set: Mapped["AbilityRollSet | None"] = relationship(
        "AbilityRollSet", back_populates="character", uselist=False
    )


if TYPE_CHECKING:
    from app.models.ability_roll import AbilityRollSet
    from app.models.campaign import CampaignMember
    from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog
