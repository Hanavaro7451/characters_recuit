from sqlalchemy import UniqueConstraint, inspect
from sqlalchemy.orm import configure_mappers

from app.domain.enums import CharacterStatus
from app.models import CampaignMember, Character
from app.models.base import Base


def test_character_is_registered_and_foreign_keys_resolve() -> None:
    configure_mappers()

    assert Base.metadata.tables["characters"] is Character.__table__
    tables = [table.name for table in Base.metadata.sorted_tables]
    assert tables.index("campaign_members") < tables.index("characters")
    foreign_key = next(iter(Character.__table__.c.campaign_member_id.foreign_keys))
    assert foreign_key.column is CampaignMember.__table__.c.id
    assert foreign_key.ondelete != "CASCADE"


def test_character_membership_is_required_and_unique_regardless_of_status() -> None:
    table = Character.__table__

    assert table.c.campaign_member_id.nullable is False
    assert any(
        isinstance(constraint, UniqueConstraint)
        and list(constraint.columns.keys()) == ["campaign_member_id"]
        for constraint in table.constraints
    )


def test_character_has_draft_default_and_optional_archive_reason() -> None:
    table = Character.__table__

    assert table.c.status.nullable is False
    assert table.c.status.default.arg == CharacterStatus.DRAFT
    assert table.c.archive_reason.nullable is True
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False


def test_character_membership_relationship_is_scalar_and_bidirectional() -> None:
    member = CampaignMember(id=1, campaign_id=10, user_id=2)
    assert member.character is None

    character = Character(campaign_member=member)

    assert member.character is character
    assert character.campaign_member is member
    relationship = inspect(CampaignMember).relationships.character
    assert relationship.uselist is False
    assert "delete" not in relationship.cascade
    assert "delete-orphan" not in relationship.cascade
    assert inspect(Character).relationships.campaign_member.uselist is False
