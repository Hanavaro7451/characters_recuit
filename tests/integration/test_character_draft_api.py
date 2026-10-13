import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.catalog_seed import seed_catalogs
from app.domain.enums import CampaignStatus, CharacterStatus
from app.models import (
    BackgroundCatalog,
    Campaign,
    CampaignMember,
    Character,
    ClassCatalog,
    SpeciesCatalog,
)
from tests.integration.test_auth_api import register_and_login


def auth(pair: dict[str, str]) -> dict[str, str]:
    return {"Authorization": "Bearer " + pair["access_token"]}


async def new_user(client, label: str) -> tuple[dict[str, str], int]:
    pair = await register_and_login(client, f"{label}-{uuid.uuid4().hex[:10]}")
    response = await client.get("/api/v1/users/me", headers=auth(pair))
    assert response.status_code == 200, response.text
    return pair, response.json()["id"]


async def setup_world(client, database_engine, player_count: int = 2):
    master, _ = await new_user(client, "master")
    created = await client.post(
        "/api/v1/campaigns/", json={"name": "Draft campaign"}, headers=auth(master)
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    invitation = await client.get(
        f"/api/v1/campaigns/{campaign_id}/invite", headers=auth(master)
    )
    assert invitation.status_code == 200, invitation.text
    invite_code = invitation.json()["invite_code"]

    players = []
    for _ in range(player_count):
        player, owner_id = await new_user(client, "player")
        joined = await client.post(
            "/api/v1/campaigns/join",
            json={"invite_code": invite_code},
            headers=auth(player),
        )
        assert joined.status_code == 201, joined.text
        players.append((player, owner_id))

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        await seed_catalogs(session)
        await session.commit()
        species_id = await session.scalar(
            select(SpeciesCatalog.id).where(SpeciesCatalog.code == "human")
        )
        class_id = await session.scalar(
            select(ClassCatalog.id).where(ClassCatalog.code == "fighter")
        )
        background_id = await session.scalar(
            select(BackgroundCatalog.id).where(BackgroundCatalog.code == "acolyte")
        )
    catalogs = {
        "species_id": species_id,
        "class_catalog_id": class_id,
        "background_id": background_id,
    }
    assert all(catalogs.values())
    return {
        "master": master,
        "campaign_id": campaign_id,
        "players": players,
        "catalogs": catalogs,
    }


async def create_character(client, world, player_index: int = 0, **overrides):
    player, _ = world["players"][player_index]
    payload = {"name": "Mira", **world["catalogs"], **overrides}
    response = await client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json=payload,
        headers=auth(player),
    )
    return response


def character_url(campaign_id: int, character_id: int) -> str:
    return f"/api/v1/campaigns/{campaign_id}/characters/{character_id}"


def all_json_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(all_json_keys(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(all_json_keys(child) for child in value))
    return set()


async def test_character_routes_require_valid_access_token(api_client, database_engine):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = character_url(world["campaign_id"], character_id)

    create_without_auth = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json={"name": "Mira", **world["catalogs"]},
    )
    assert create_without_auth.status_code == 401
    assert (await api_client.get(url)).status_code == 401
    assert (
        await api_client.patch(url, json={"expected_version": 1, "name": "New"})
    ).status_code == 401

    bad_headers = {"Authorization": "Bearer invalid-token"}
    assert (
        await api_client.get(url, headers=bad_headers)
    ).status_code == 401
    for path in (
        "/api/v1/catalog/species",
        "/api/v1/catalog/classes",
        "/api/v1/catalog/backgrounds",
        f"/api/v1/catalog/species/{world['catalogs']['species_id']}",
    ):
        assert (await api_client.get(path)).status_code == 401


async def test_player_owner_and_master_read_access_hides_private_notes(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=2)
    created = await create_character(api_client, world, name="Owner's hero")
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = character_url(world["campaign_id"], character_id)

    owner = world["players"][0][0]
    other_player = world["players"][1][0]
    for reader in (owner, other_player, world["master"]):
        response = await api_client.get(url, headers=auth(reader))
        if reader is other_player:
            assert response.status_code == 404
            assert "Owner's hero" not in response.text
        else:
            assert response.status_code == 200, response.text
            assert "private_notes" not in all_json_keys(response.json())
    rejected_patch = await api_client.patch(
        url,
        json={"expected_version": 1, "name": "Stolen edit"},
        headers=auth(other_player),
    )
    assert rejected_patch.status_code == 404
    body = (await api_client.get(url, headers=auth(owner))).json()
    assert body["name"] == "Owner's hero"
    assert body["owner_user_id"] == world["players"][0][1]
    assert body["campaign_id"] == world["campaign_id"]


async def test_campaign_and_character_id_substitution_is_not_found(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=2)
    first = await create_character(api_client, world, player_index=0, name="First")
    second = await create_character(api_client, world, player_index=1, name="Second")
    assert first.status_code == second.status_code == 201
    outsider, _ = await new_user(api_client, "outsider")

    second_campaign = await api_client.post(
        "/api/v1/campaigns/",
        json={"name": "Unrelated campaign"},
        headers=auth(outsider),
    )
    assert second_campaign.status_code == 201, second_campaign.text
    other_campaign_id = second_campaign.json()["id"]
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    attempts = [
        (world["players"][0][0], other_campaign_id, first_id),
        (world["players"][0][0], world["campaign_id"], second_id),
        (outsider, world["campaign_id"], first_id),
        (world["master"], other_campaign_id, first_id),
    ]
    for reader, campaign_id, character_id in attempts:
        response = await api_client.get(
            character_url(campaign_id, character_id), headers=auth(reader)
        )
        assert response.status_code == 404
        assert "First" not in response.text
    for campaign_id, character_id in (
        (other_campaign_id, first_id),
        (world["campaign_id"], second_id),
    ):
        response = await api_client.patch(
            character_url(campaign_id, character_id),
            json={"expected_version": 1, "name": "IDOR edit"},
            headers=auth(world["players"][0][0]),
        )
        assert response.status_code == 404


async def test_master_cannot_create_or_patch_and_unjoined_player_gets_404(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json={"name": "Master character", **world["catalogs"]},
        headers=auth(world["master"]),
    )
    assert created.status_code == 403

    character = await create_character(api_client, world)
    assert character.status_code == 201, character.text
    url = character_url(world["campaign_id"], character.json()["id"])
    patch = await api_client.patch(
        url,
        json={"expected_version": 1, "name": "Forbidden"},
        headers=auth(world["master"]),
    )
    assert patch.status_code == 403

    outsider, _ = await new_user(api_client, "outsider")
    outside_create = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json={"name": "Outside", **world["catalogs"]},
        headers=auth(outsider),
    )
    assert outside_create.status_code == 404


async def test_creation_derives_owner_and_sets_draft_defaults(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    response = await create_character(api_client, world, name="  Mira  ")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["campaign_id"] == world["campaign_id"]
    assert body["owner_user_id"] == world["players"][0][1]
    assert body["name"] == "Mira"
    assert body["status"] == "draft"
    assert body["level"] == 1
    assert body["version"] == 1
    assert body["species"]["id"] == world["catalogs"]["species_id"]
    assert body["character_class"]["id"] == world["catalogs"]["class_catalog_id"]
    assert body["background"]["id"] == world["catalogs"]["background_id"]
    assert "campaign_member_id" not in body
    assert "private_notes" not in all_json_keys(body)


async def test_duplicate_creation_returns_conflict_even_after_archive(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    duplicate = await create_character(api_client, world, name="Replacement")
    assert duplicate.status_code == 409

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, created.json()["id"])
        assert character is not None
        character.status = CharacterStatus.ARCHIVED
        await session.commit()

    archived_duplicate = await create_character(
        api_client, world, name="Still a duplicate"
    )
    assert archived_duplicate.status_code == 409


async def test_concurrent_creation_has_exactly_one_winner(api_client, database_engine):
    world = await setup_world(api_client, database_engine, player_count=1)
    barrier = asyncio.Barrier(2)

    async def create(name: str):
        await barrier.wait()
        return await create_character(api_client, world, name=name)

    responses = await asyncio.gather(create("Concurrent A"), create("Concurrent B"))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner = next(
        response.json() for response in responses if response.status_code == 201
    )
    url = character_url(world["campaign_id"], winner["id"])
    stored = await api_client.get(url, headers=auth(world["players"][0][0]))
    assert stored.status_code == 200
    assert stored.json()["name"] in {"Concurrent A", "Concurrent B"}


async def test_completed_campaign_rejects_create_and_patch_but_allows_get(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        campaign = await session.get(Campaign, world["campaign_id"])
        assert campaign is not None
        campaign.status = CampaignStatus.COMPLETED
        await session.commit()

    read = await api_client.get(
        character_url(world["campaign_id"], character_id),
        headers=auth(world["players"][0][0]),
    )
    assert read.status_code == 200
    rejected_create = await create_character(api_client, world, name="Late arrival")
    assert rejected_create.status_code == 409
    rejected_patch = await api_client.patch(
        character_url(world["campaign_id"], character_id),
        json={"expected_version": 1, "name": "Late edit"},
        headers=auth(world["players"][0][0]),
    )
    assert rejected_patch.status_code == 409


@pytest.mark.parametrize(
    "field",
    ["species_id", "class_catalog_id", "background_id"],
)
async def test_creation_rejects_unknown_catalog_ids(api_client, database_engine, field):
    world = await setup_world(api_client, database_engine, player_count=1)
    payload = {"name": "Invalid reference", **world["catalogs"], field: 987654321}
    response = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json=payload,
        headers=auth(world["players"][0][0]),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    ["species_id", "class_catalog_id", "background_id"],
)
async def test_creation_rejects_closed_catalog_versions(
    api_client, database_engine, field
):
    world = await setup_world(api_client, database_engine, player_count=1)
    model = {
        "species_id": SpeciesCatalog,
        "class_catalog_id": ClassCatalog,
        "background_id": BackgroundCatalog,
    }[field]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        catalog_id = world["catalogs"][field]
        item = await session.get(model, catalog_id)
        assert item is not None
        item.available_for_selection = False
        await session.commit()
    payload = {"name": "Closed reference", **world["catalogs"]}
    response = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json={**payload, field: world["catalogs"][field]},
        headers=auth(world["players"][0][0]),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "model"),
    [
        ("species_id", SpeciesCatalog),
        ("class_catalog_id", ClassCatalog),
        ("background_id", BackgroundCatalog),
    ],
)
async def test_creation_rejects_catalog_from_another_ruleset(
    api_client, database_engine, field, model
):
    world = await setup_world(api_client, database_engine, player_count=1)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        values = {
            "code": f"foreign-{field}",
            "ruleset": "dnd-2014",
            "content_version": "2014-snapshot",
            "name": "Human",
            "description": "An intentionally incompatible test version.",
            "source_title": "Test source",
            "source_url": "https://example.invalid/legacy",
            "license_name": "CC-BY-4.0",
            "attribution": "Test attribution",
            "available_for_selection": True,
        }
        if model is BackgroundCatalog:
            values.update(
                ability_one="STR",
                ability_two="DEX",
                ability_three="CON",
                allow_plus_two_plus_one=True,
                allow_plus_one_each=True,
            )
        foreign_ruleset = model(**values)
        session.add(foreign_ruleset)
        await session.commit()
        foreign_catalog_id = foreign_ruleset.id

    payload = {**world["catalogs"], "name": "Wrong ruleset"}
    payload[field] = foreign_catalog_id
    response = await api_client.post(
        f"/api/v1/campaigns/{world['campaign_id']}/characters",
        json=payload,
        headers=auth(world["players"][0][0]),
    )
    assert response.status_code == 422


async def test_closed_pinned_catalog_version_remains_readable(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    species_id = world["catalogs"]["species_id"]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        species = await session.get(SpeciesCatalog, species_id)
        assert species is not None
        species.available_for_selection = False
        await session.commit()

    item_response = await api_client.get(
        f"/api/v1/catalog/species/{species_id}",
        headers=auth(world["players"][0][0]),
    )
    assert item_response.status_code == 200
    assert item_response.json()["available_for_selection"] is False
    listing = await api_client.get(
        "/api/v1/catalog/species?ruleset=dnd-2024",
        headers=auth(world["players"][0][0]),
    )
    assert listing.status_code == 200
    assert species_id not in {item["id"] for item in listing.json()}

    character_response = await api_client.get(
        character_url(world["campaign_id"], character_id),
        headers=auth(world["players"][0][0]),
    )
    assert character_response.status_code == 200
    assert character_response.json()["species"]["id"] == species_id
    assert character_response.json()["species"]["available_for_selection"] is False


async def test_patch_omitted_fields_are_preserved_and_null_is_rejected(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = character_url(world["campaign_id"], character_id)
    player = world["players"][0][0]

    renamed = await api_client.patch(
        url,
        json={"expected_version": 1, "name": "  New name  "},
        headers=auth(player),
    )
    assert renamed.status_code == 200, renamed.text
    updated = renamed.json()
    assert updated["name"] == "New name"
    assert updated["version"] == 2
    for field in ("species_id", "class_catalog_id", "background_id"):
        assert updated[{
            "species_id": "species",
            "class_catalog_id": "character_class",
            "background_id": "background",
        }[field]]["id"] == world["catalogs"][field]

    for field in ("name", "species_id", "class_catalog_id", "background_id"):
        response = await api_client.patch(
            url,
            json={"expected_version": 2, field: None},
            headers=auth(player),
        )
        assert response.status_code == 422
    unchanged = await api_client.get(url, headers=auth(player))
    assert unchanged.status_code == 200
    assert unchanged.json()["name"] == "New name"
    assert unchanged.json()["version"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": 1},
        {"expected_version": 0, "name": "Invalid version"},
        {"expected_version": 1, "name": "   "},
        {"expected_version": 1, "name": "x" * 256},
        {"expected_version": 1, "name": "Valid", "level": 2},
        {"expected_version": 1, "name": "Valid", "status": "active"},
        {"expected_version": 1, "name": "Valid", "owner_user_id": 999},
        {"expected_version": 1, "name": "Valid", "campaign_member_id": 999},
        {"expected_version": 1, "name": "Valid", "unknown": "field"},
    ],
)
async def test_patch_rejects_empty_invalid_and_unknown_fields(
    api_client, database_engine, payload
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    url = character_url(world["campaign_id"], created.json()["id"])
    response = await api_client.patch(
        url, json=payload, headers=auth(world["players"][0][0])
    )
    assert response.status_code == 422
    current = await api_client.get(url, headers=auth(world["players"][0][0]))
    assert current.status_code == 200
    assert current.json()["name"] == "Mira"
    assert current.json()["version"] == 1


async def test_patch_rejects_non_draft_character(api_client, database_engine):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, character_id)
        assert character is not None
        character.status = CharacterStatus.ACTIVE
        await session.commit()

    response = await api_client.patch(
        character_url(world["campaign_id"], character_id),
        json={"expected_version": 1, "name": "No longer a draft"},
        headers=auth(world["players"][0][0]),
    )
    assert response.status_code == 409


async def test_stale_patch_returns_conflict_without_changing_saved_data(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    url = character_url(world["campaign_id"], created.json()["id"])
    player = world["players"][0][0]
    winning = await api_client.patch(
        url, json={"expected_version": 1, "name": "Saved"}, headers=auth(player)
    )
    assert winning.status_code == 200, winning.text
    stale = await api_client.patch(
        url,
        json={"expected_version": 1, "name": "Stale overwrite"},
        headers=auth(player),
    )
    assert stale.status_code == 409
    stored = await api_client.get(url, headers=auth(player))
    assert stored.status_code == 200
    assert stored.json()["name"] == "Saved"
    assert stored.json()["version"] == 2


async def test_concurrent_patches_do_not_silently_overwrite_each_other(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    url = character_url(world["campaign_id"], created.json()["id"])
    player = world["players"][0][0]
    alternate_species = SpeciesCatalog(
        code="elf-for-patch",
        ruleset="dnd-2024",
        content_version="test-1",
        name="Elf",
        description="A patch candidate.",
        source_title="Test source",
        source_url="https://example.invalid/elf",
        license_name="CC-BY-4.0",
        attribution="Test attribution",
        available_for_selection=True,
    )
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(alternate_species)
        await session.commit()
        alternate_species_id = alternate_species.id

    barrier = asyncio.Barrier(2)

    async def patch(payload):
        await barrier.wait()
        return await api_client.patch(url, json=payload, headers=auth(player))

    responses = await asyncio.gather(
        patch({"expected_version": 1, "name": "Concurrent name"}),
        patch({"expected_version": 1, "species_id": alternate_species_id}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    stored = await api_client.get(url, headers=auth(player))
    assert stored.status_code == 200
    current = stored.json()
    assert current["version"] == 2
    assert current["name"] == winner["name"]
    assert current["species"]["id"] == winner["species"]["id"]
    assert (current["name"], current["species"]["id"]) in {
        ("Concurrent name", world["catalogs"]["species_id"]),
        ("Mira", alternate_species_id),
    }


async def test_legacy_nullable_character_fields_are_readable(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    owner_pair, owner_id = world["players"][0]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        membership = await session.scalar(
            select(CampaignMember).where(
                CampaignMember.campaign_id == world["campaign_id"],
                CampaignMember.user_id == owner_id,
            )
        )
        assert membership is not None
        legacy = Character(
            campaign_member_id=membership.id,
            name="Legacy sheet",
            race="Old race text",
            character_class="Old class text",
            species_id=None,
            class_catalog_id=None,
            background_id=None,
        )
        session.add(legacy)
        await session.commit()
        character_id = legacy.id

    response = await api_client.get(
        character_url(world["campaign_id"], character_id), headers=auth(owner_pair)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["legacy_race"] == "Old race text"
    assert body["legacy_character_class"] == "Old class text"
    assert body["species"] is None
    assert body["character_class"] is None
    assert body["background"] is None
