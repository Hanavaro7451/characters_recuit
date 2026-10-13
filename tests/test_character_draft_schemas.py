import pytest
from pydantic import ValidationError

from app.schemas.character import CharacterCreate, CharacterPatch


def valid_character_payload() -> dict[str, object]:
    return {
        "name": "Mira",
        "species_id": 1,
        "class_catalog_id": 2,
        "background_id": 3,
    }


def test_character_create_requires_all_catalogs_and_trims_name() -> None:
    payload = valid_character_payload()
    payload["name"] = "  Mira  "

    request = CharacterCreate.model_validate(payload)

    assert request.name == "Mira"
    assert request.species_id == 1
    assert request.class_catalog_id == 2
    assert request.background_id == 3


@pytest.mark.parametrize(
    "field",
    ["name", "species_id", "class_catalog_id", "background_id"],
)
def test_character_create_rejects_missing_required_fields(field: str) -> None:
    payload = valid_character_payload()
    del payload[field]

    with pytest.raises(ValidationError):
        CharacterCreate.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["species_id", "class_catalog_id", "background_id"]
)
@pytest.mark.parametrize("value", [0, -1, None, "not-an-id"])
def test_character_create_rejects_invalid_catalog_ids(
    field: str, value: object
) -> None:
    payload = valid_character_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        CharacterCreate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"campaign_id": 4},
        {"owner_user_id": 5},
        {"campaign_member_id": 6},
        {"status": "active"},
        {"level": 2},
        {"private_notes": "hidden"},
    ],
)
def test_character_create_forbids_server_owned_or_unknown_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CharacterCreate.model_validate({**valid_character_payload(), **payload})


def test_character_patch_preserves_omitted_fields() -> None:
    request = CharacterPatch.model_validate({"expected_version": 1, "name": "New"})

    assert request.model_dump(exclude_unset=True, exclude={"expected_version"}) == {
        "name": "New"
    }


@pytest.mark.parametrize(
    "field", ["name", "species_id", "class_catalog_id", "background_id"]
)
def test_character_patch_rejects_explicit_null(field: str) -> None:
    with pytest.raises(ValidationError):
        CharacterPatch.model_validate({"expected_version": 1, field: None})


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": 1},
        {"expected_version": 0, "name": "New"},
        {"expected_version": -1, "name": "New"},
        {"expected_version": 1, "status": "active"},
        {"expected_version": 1, "level": 2},
        {"expected_version": 1, "owner_user_id": 5},
        {"expected_version": 1, "campaign_member_id": 6},
        {"expected_version": 1, "unknown": "field"},
    ],
)
def test_character_patch_rejects_empty_invalid_and_unknown_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CharacterPatch.model_validate(payload)
