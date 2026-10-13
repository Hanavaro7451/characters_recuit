import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.enums import CampaignStatus, CharacterStatus
from app.models import (
    AbilityRollResult,
    AbilityRollSet,
    BackgroundCatalog,
    Campaign,
    Character,
    ClassCatalog,
    SpeciesCatalog,
)
from app.services.ability_roll import RollOutcome
from tests.integration.test_auth_api import register_and_login
from tests.integration.test_character_draft_api import (
    auth,
    character_url,
    create_character,
    setup_world,
)


def rolls_url(campaign_id: int, character_id: int) -> str:
    return f"{character_url(campaign_id, character_id)}/ability-rolls"


def assert_roll_set(body: dict, character_id: int) -> None:
    assert body["character_id"] == character_id
    assert body["id"]
    assert body["generated_at"]
    results = body["results"]
    assert len(results) == 6
    assert [result["position"] for result in results] == list(range(1, 7))
    assert len({result["id"] for result in results}) == 6
    for result in results:
        dice = result["dice"]
        assert len(dice) == 4
        assert all(1 <= die <= 6 for die in dice)
        assert 0 <= result["dropped_index"] < 4
        assert dice[result["dropped_index"]] == min(dice)
        assert result["total"] == sum(dice) - dice[result["dropped_index"]]
        assert 3 <= result["total"] <= 18


async def test_rolls_are_absent_until_first_generation(api_client, database_engine):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    player = world["players"][0][0]
    url = rolls_url(world["campaign_id"], created.json()["id"])

    missing = await api_client.get(url, headers=auth(player))
    assert missing.status_code == 404, missing.text
    generated = await api_client.post(url, headers=auth(player))
    assert generated.status_code == 201, generated.text
    assert_roll_set(generated.json(), created.json()["id"])


async def test_roll_generation_is_idempotent_and_does_not_advance_character_version(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    player = world["players"][0][0]
    url = rolls_url(world["campaign_id"], character_id)
    character = character_url(world["campaign_id"], character_id)

    first = await api_client.post(url, json={}, headers=auth(player))
    assert first.status_code == 201, first.text
    assert_roll_set(first.json(), character_id)
    after_first = await api_client.get(character, headers=auth(player))
    assert after_first.status_code == 200
    assert after_first.json()["version"] == 2

    repeated = await api_client.post(url, headers=auth(player))
    read_again = await api_client.get(url, headers=auth(player))
    assert repeated.status_code == 200, repeated.text
    assert read_again.status_code == 200, read_again.text
    assert repeated.json() == first.json()
    assert read_again.json() == first.json()
    unchanged = await api_client.get(character, headers=auth(player))
    assert unchanged.json()["version"] == 2


async def test_parallel_requests_over_separate_http_requests_return_same_set(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)
    player = world["players"][0][0]
    barrier = asyncio.Barrier(6)

    async def generate():
        await barrier.wait()
        return await api_client.post(url, headers=auth(player))

    responses = await asyncio.gather(*(generate() for _ in range(6)))
    assert all(response.status_code in {200, 201} for response in responses), [
        (response.status_code, response.text) for response in responses
    ]
    assert sum(response.status_code == 201 for response in responses) == 1
    payloads = [response.json() for response in responses]
    assert all(payload == payloads[0] for payload in payloads)
    assert_roll_set(payloads[0], character_id)

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        stored = await session.get(Character, character_id)
        assert stored is not None
        assert stored.version == 2


async def test_failed_result_insert_rolls_back_entire_set_and_version(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)
    player = world["players"][0][0]

    async with database_engine.begin() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
        assert schema and schema.startswith("qa_")
        await connection.execute(
            text(
                f'''CREATE FUNCTION "{schema}".reject_ability_roll_result()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                        IF NEW.position = 3 THEN
                            RAISE EXCEPTION 'forced QA insert failure';
                        END IF;
                        RETURN NEW;
                    END;
                    $$'''
            )
        )
        await connection.execute(
            text(
                f'''CREATE TRIGGER qa_reject_ability_roll_result
                    BEFORE INSERT ON ability_roll_results
                    FOR EACH ROW EXECUTE FUNCTION
                    "{schema}".reject_ability_roll_result()'''
            )
        )

    transport = ASGITransport(
        app=api_client._transport.app, raise_app_exceptions=False
    )
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as failing_client:
        failed = await failing_client.post(url, headers=auth(player))
    assert failed.status_code == 500

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(AbilityRollSet).where(
                AbilityRollSet.character_id == character_id
            )
        ) == 0
        assert await session.scalar(
            select(func.count())
            .select_from(AbilityRollResult)
            .join(AbilityRollSet)
            .where(AbilityRollSet.character_id == character_id)
        ) == 0
        character = await session.get(Character, character_id)
        assert character is not None
        assert character.version == 1


async def test_post_rejects_client_supplied_dice_or_seed_without_generating(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)
    player = world["players"][0][0]

    for payload in (
        {"dice": [6] * 24},
        {"seed": "client-controlled"},
        {"results": [18] * 6},
    ):
        rejected = await api_client.post(url, json=payload, headers=auth(player))
        assert rejected.status_code == 422, rejected.text
    assert (await api_client.get(url, headers=auth(player))).status_code == 404
    character = await api_client.get(
        character_url(world["campaign_id"], character_id), headers=auth(player)
    )
    assert character.json()["version"] == 1


async def test_owner_master_and_foreign_user_access(api_client, database_engine):
    world = await setup_world(api_client, database_engine, player_count=2)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)
    owner, other_player = world["players"][0][0], world["players"][1][0]
    generated = await api_client.post(url, headers=auth(owner))
    assert generated.status_code == 201, generated.text

    owner_read = await api_client.get(url, headers=auth(owner))
    master_read = await api_client.get(url, headers=auth(world["master"]))
    assert owner_read.status_code == 200
    assert master_read.status_code == 200
    assert owner_read.json() == generated.json() == master_read.json()

    assert (await api_client.get(url, headers=auth(other_player))).status_code == 404
    assert (await api_client.post(url, headers=auth(other_player))).status_code == 404

    outsider = await register_and_login(
        api_client, f"outsider-{uuid.uuid4().hex[:10]}"
    )
    assert (await api_client.get(url, headers=auth(outsider))).status_code == 404
    assert (await api_client.post(url, headers=auth(outsider))).status_code == 404


async def test_roll_routes_require_authentication_and_positive_ids(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)

    assert (await api_client.get(url)).status_code == 401
    assert (await api_client.post(url)).status_code == 401
    bad_token = {"Authorization": "Bearer not-a-real-access-token"}
    assert (await api_client.get(url, headers=bad_token)).status_code == 401
    assert (await api_client.post(url, headers=bad_token)).status_code == 401
    owner = world["players"][0][0]
    assert (
        await api_client.get(rolls_url(0, character_id), headers=auth(owner))
    ).status_code == 422
    assert (
        await api_client.post(rolls_url(world["campaign_id"], 0), headers=auth(owner))
    ).status_code == 422


async def test_master_cannot_generate_and_wrong_campaign_or_character_ids_are_hidden(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)

    forbidden = await api_client.post(url, headers=auth(world["master"]))
    assert forbidden.status_code == 403
    assert (await api_client.get(url, headers=auth(world["master"]))).status_code == 404

    owner = world["players"][0][0]
    foreign_campaign_id = world["campaign_id"] + 100000
    foreign_character_id = character_id + 100000
    for method in ("get", "post"):
        for target in (
            rolls_url(foreign_campaign_id, character_id),
            rolls_url(world["campaign_id"], foreign_character_id),
        ):
            response = await getattr(api_client, method)(target, headers=auth(owner))
            assert response.status_code == 404, response.text


@pytest.mark.parametrize(
    ("character_status", "campaign_status"),
    [
        (CharacterStatus.ACTIVE, CampaignStatus.ACTIVE),
        (CharacterStatus.ARCHIVED, CampaignStatus.ACTIVE),
        (CharacterStatus.DRAFT, CampaignStatus.COMPLETED),
    ],
)
async def test_post_rejects_inactive_state_but_saved_set_remains_readable(
    api_client, database_engine, character_status, campaign_status
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    url = rolls_url(world["campaign_id"], character_id)
    owner = world["players"][0][0]
    generated = await api_client.post(url, headers=auth(owner))
    assert generated.status_code == 201, generated.text

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, character_id)
        campaign = await session.get(Campaign, world["campaign_id"])
        assert character is not None and campaign is not None
        character.status = character_status
        campaign.status = campaign_status
        await session.commit()

    denied = await api_client.post(url, headers=auth(owner))
    assert denied.status_code == 409, denied.text
    owner_read = await api_client.get(url, headers=auth(owner))
    master_read = await api_client.get(url, headers=auth(world["master"]))
    assert owner_read.status_code == master_read.status_code == 200
    assert owner_read.json() == master_read.json() == generated.json()


async def test_roll_set_survives_character_patch_and_stale_patch_is_rejected(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    owner = world["players"][0][0]
    url = rolls_url(world["campaign_id"], character_id)
    character = character_url(world["campaign_id"], character_id)
    generated = await api_client.post(url, headers=auth(owner))
    assert generated.status_code == 201, generated.text

    stale = await api_client.patch(
        character,
        json={"expected_version": 1, "name": "Stale name"},
        headers=auth(owner),
    )
    assert stale.status_code == 409
    renamed = await api_client.patch(
        character,
        json={"expected_version": 2, "name": "Renamed"},
        headers=auth(owner),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["version"] == 3

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        species = SpeciesCatalog(
            code=f"elf-{uuid.uuid4().hex[:8]}",
            ruleset="dnd-2024",
            content_version="test-1",
            name="Elf",
            description="A second species version for this test.",
            source_title="Test source",
            source_url="https://example.invalid/elf",
            license_name="CC-BY-4.0",
            attribution="Test attribution",
            available_for_selection=True,
        )
        character_class = ClassCatalog(
            code=f"wizard-{uuid.uuid4().hex[:8]}",
            ruleset="dnd-2024",
            content_version="test-1",
            name="Wizard",
            description="A second class version for this test.",
            source_title="Test source",
            source_url="https://example.invalid/wizard",
            license_name="CC-BY-4.0",
            attribution="Test attribution",
            available_for_selection=True,
        )
        background = BackgroundCatalog(
            code=f"sage-{uuid.uuid4().hex[:8]}",
            ruleset="dnd-2024",
            content_version="test-1",
            name="Sage",
            description="A second background version for this test.",
            source_title="Test source",
            source_url="https://example.invalid/sage",
            license_name="CC-BY-4.0",
            attribution="Test attribution",
            available_for_selection=True,
            ability_one="INT",
            ability_two="WIS",
            ability_three="CHA",
            allow_plus_two_plus_one=True,
            allow_plus_one_each=True,
        )
        session.add_all([species, character_class, background])
        await session.commit()
        replacements = {
            "species_id": species.id,
            "class_catalog_id": character_class.id,
            "background_id": background.id,
        }

    changed_catalogs = await api_client.patch(
        character,
        json={
            "expected_version": 3,
            **replacements,
        },
        headers=auth(owner),
    )
    assert changed_catalogs.status_code == 200, changed_catalogs.text
    assert changed_catalogs.json()["version"] == 4
    assert changed_catalogs.json()["species"]["id"] == replacements["species_id"]
    assert (
        changed_catalogs.json()["character_class"]["id"]
        == replacements["class_catalog_id"]
    )
    assert (
        changed_catalogs.json()["background"]["id"]
        == replacements["background_id"]
    )

    read = await api_client.get(url, headers=auth(owner))
    assert read.status_code == 200, read.text
    assert read.json() == generated.json()


async def test_equal_totals_are_valid_with_distinct_result_ids(
    api_client, database_engine, monkeypatch
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    player = world["players"][0][0]
    outcomes = [
        RollOutcome(position, (2, 2, 2, 2), 0, 6) for position in range(1, 7)
    ]
    monkeypatch.setattr("app.services.character.generate_rolls", lambda: outcomes)
    response = await api_client.post(
        rolls_url(world["campaign_id"], created.json()["id"]),
        headers=auth(player),
    )
    assert response.status_code == 201, response.text
    results = response.json()["results"]
    assert [result["total"] for result in results] == [6] * 6
    assert len({result["id"] for result in results}) == 6
