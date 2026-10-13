import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.enums import CampaignStatus, CharacterStatus
from app.models import (
    AbilityDistribution,
    AbilityRollResult,
    BackgroundCatalog,
    Campaign,
    Character,
)
from tests.integration.test_character_ability_rolls_api import rolls_url
from tests.integration.test_character_draft_api import (
    auth,
    character_url,
    create_character,
    new_user,
    setup_world,
)

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


def distribution_url(campaign_id: int, character_id: int) -> str:
    return f"{character_url(campaign_id, character_id)}/ability-distribution"


async def create_rolled_character(api_client, database_engine, world, player_index=0):
    created = await create_character(api_client, world, player_index)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]
    player = world["players"][player_index][0]
    rolled = await api_client.post(
        rolls_url(world["campaign_id"], character_id), headers=auth(player)
    )
    assert rolled.status_code == 201, rolled.text
    return created.json(), rolled.json()


async def set_roll_totals(database_engine, roll_set_id: int, totals: list[int]) -> None:
    dice_for_total = {
        3: (1, 1, 1, 1),
        7: (1, 1, 2, 4),
        9: (1, 2, 3, 4),
        10: (1, 3, 3, 4),
        12: (1, 3, 4, 5),
        14: (1, 3, 5, 6),
        16: (1, 5, 5, 6),
        18: (6, 6, 6, 6),
    }
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        results = list(
            (
                await session.scalars(
                    select(AbilityRollResult)
                    .where(AbilityRollResult.roll_set_id == roll_set_id)
                    .order_by(AbilityRollResult.position)
                )
            ).all()
        )
        assert len(results) == 6
        for result, total in zip(results, totals, strict=True):
            dice = dice_for_total[total]
            result.die_one, result.die_two, result.die_three, result.die_four = dice
            result.dropped_index = 0
            result.total = total
        await session.commit()


def assignments_for(results: list[dict]) -> dict[str, int]:
    return {
        ability: result["id"]
        for ability, result in zip(ABILITIES, results, strict=True)
    }


def plus_two_choice(plus_two: str = "STR", plus_one: str = "DEX") -> dict:
    return {
        "pattern": "plus_two_plus_one",
        "plus_two": plus_two,
        "plus_one": plus_one,
    }


def save_payload(rolls: dict, expected_version: int = 2, **overrides) -> dict:
    return {
        "expected_version": expected_version,
        "assignments": assignments_for(rolls["results"]),
        "bonus_choice": plus_two_choice("INT", "WIS"),
        **overrides,
    }


async def insert_background(
    database_engine,
    code: str,
    targets: tuple[str, str, str],
    allow_plus_two_plus_one: bool = True,
    allow_plus_one_each: bool = True,
) -> int:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        background = BackgroundCatalog(
            ruleset="dnd-2024",
            code=code,
            content_version="qa-1",
            name=f"QA {code}",
            description="Каталог для изолированного API-теста.",
            source_title="QA fixture",
            source_url="https://example.test/qa",
            license_name="CC-BY-4.0",
            attribution="Тестовая запись.",
            available_for_selection=True,
            ability_one=targets[0],
            ability_two=targets[1],
            ability_three=targets[2],
            allow_plus_two_plus_one=allow_plus_two_plus_one,
            allow_plus_one_each=allow_plus_one_each,
        )
        session.add(background)
        await session.flush()
        background_id = background.id
        await session.commit()
        return background_id


async def test_get_distribution_is_empty_before_rolls_and_after_rolls(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created.json()["id"])

    before_rolls = await api_client.get(url, headers=auth(player))
    assert before_rolls.status_code == 200, before_rolls.text
    assert before_rolls.json()["has_rolls"] is False
    assert before_rolls.json()["assignment_complete"] is False
    assert before_rolls.json()["bonus_complete"] is False
    assert before_rolls.json()["complete"] is False
    assert before_rolls.json()["bonus_choice"] is None
    assert all(item["base_value"] is None for item in before_rolls.json()["abilities"])
    unavailable = await api_client.put(
        url,
        json={
            "expected_version": 1,
            "assignments": {
                ability: index + 1 for index, ability in enumerate(ABILITIES)
            },
            "bonus_choice": plus_two_choice("INT", "WIS"),
        },
        headers=auth(player),
    )
    assert unavailable.status_code == 409

    rolled = await api_client.post(
        rolls_url(world["campaign_id"], created.json()["id"]),
        headers=auth(player),
    )
    assert rolled.status_code == 201, rolled.text
    after_rolls = await api_client.get(url, headers=auth(player))
    assert after_rolls.status_code == 200, after_rolls.text
    assert after_rolls.json()["has_rolls"] is True
    assert after_rolls.json()["assignment_complete"] is False
    assert after_rolls.json()["bonus_complete"] is False
    assert after_rolls.json()["complete"] is False
    assert all(
        item["roll_result_id"] is None for item in after_rolls.json()["abilities"]
    )
    assert all(item["base_value"] is None for item in after_rolls.json()["abilities"])


async def test_put_assigns_exactly_six_distinct_roll_ids_and_calculates_values(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    await set_roll_totals(database_engine, rolls["id"], [18, 18, 9, 10, 12, 14])
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])

    response = await api_client.put(
        url,
        json=save_payload(rolls),
        headers=auth(player),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["character_id"] == created["id"]
    assert body["character_version"] == 3
    assert body["has_rolls"] is True
    assert body["assignment_complete"] is True
    assert body["bonus_complete"] is True
    assert body["complete"] is True
    assert [item["ability"] for item in body["abilities"]] == list(ABILITIES)
    assert [item["base_value"] for item in body["abilities"]] == [18, 18, 9, 10, 12, 14]
    assert [item["bonus"] for item in body["abilities"]] == [0, 0, 0, 2, 1, 0]
    assert [item["total"] for item in body["abilities"]] == [18, 18, 9, 12, 13, 14]
    assert [item["modifier"] for item in body["abilities"]] == [4, 4, -1, 1, 1, 2]
    assert all(
        item["total"] is None or item["total"] <= 20 for item in body["abilities"]
    )
    assert body["abilities"][3]["bonus_source"]["type"] == "background"
    assert body["abilities"][2]["bonus_source"] is None

    stored = await api_client.get(url, headers=auth(player))
    assert stored.status_code == 200
    assert stored.json() == body
    assert (
        await api_client.get(
            character_url(world["campaign_id"], created["id"]), headers=auth(player)
        )
    ).json()["version"] == 3


async def test_put_rejects_duplicate_missing_foreign_unknown_ids_and_client_totals(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=2)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    other_created, other_rolls = await create_rolled_character(
        api_client, database_engine, world, player_index=1
    )
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    cases = []
    duplicate = save_payload(rolls)
    duplicate["assignments"]["DEX"] = duplicate["assignments"]["STR"]
    cases.append(duplicate)
    missing = save_payload(rolls)
    del missing["assignments"]["CHA"]
    cases.append(missing)
    foreign = save_payload(rolls)
    foreign["assignments"]["STR"] = other_rolls["results"][0]["id"]
    cases.append(foreign)
    unknown = save_payload(rolls)
    unknown["assignments"]["STR"] = 2_000_000_000
    cases.append(unknown)
    for forbidden in ("total", "modifier", "base_value", "bonus"):
        client_value = save_payload(rolls)
        client_value[forbidden] = 18
        cases.append(client_value)

    for payload in cases:
        rejected = await api_client.put(url, json=payload, headers=auth(player))
        assert rejected.status_code == 422, rejected.text

    assert (await api_client.get(url, headers=auth(player))).json()["complete"] is False
    assert (
        await api_client.get(
            character_url(world["campaign_id"], created["id"]), headers=auth(player)
        )
    ).json()["version"] == 2
    assert other_created["id"] != created["id"]


async def test_bonus_patterns_follow_background_flags_and_targets(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    plus_two_plus_one = await api_client.put(
        url,
        json=save_payload(rolls, bonus_choice=plus_two_choice("CHA", "INT")),
        headers=auth(player),
    )
    assert plus_two_plus_one.status_code == 200, plus_two_plus_one.text
    assert [item["bonus"] for item in plus_two_plus_one.json()["abilities"]] == [
        0,
        0,
        0,
        1,
        0,
        2,
    ]
    assert (
        plus_two_plus_one.json()["abilities"][5]["bonus_source"]["catalog_version_id"]
        == created["background"]["id"]
    )

    # Новое распределение разрешено полным PUT, версия персонажа передаётся явно.
    plus_one_each_payload = save_payload(
        rolls, expected_version=3, bonus_choice={"pattern": "plus_one_each"}
    )
    assignments = plus_one_each_payload["assignments"]
    assignments["STR"], assignments["DEX"] = assignments["DEX"], assignments["STR"]
    plus_one_each = await api_client.put(
        url,
        json=plus_one_each_payload,
        headers=auth(player),
    )
    assert plus_one_each.status_code == 200, plus_one_each.text
    assert [item["bonus"] for item in plus_one_each.json()["abilities"]] == [
        0,
        0,
        0,
        1,
        1,
        1,
    ]
    assert (
        plus_one_each.json()["abilities"][0]["roll_result_id"]
        == rolls["results"][1]["id"]
    )
    assert (
        plus_one_each.json()["abilities"][1]["roll_result_id"]
        == rolls["results"][0]["id"]
    )


@pytest.mark.parametrize(
    "choice",
    [
        {"pattern": "plus_two_plus_one", "plus_two": "STR", "plus_one": "INT"},
        {"pattern": "plus_two_plus_one", "plus_two": "STR", "plus_one": "STR"},
        {"pattern": "plus_one_each", "targets": ["STR", "DEX", "CON"]},
        {"pattern": "plus_three", "target": "STR"},
    ],
)
async def test_put_rejects_invalid_bonus_pattern_or_targets(
    api_client, database_engine, choice
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    response = await api_client.put(
        distribution_url(world["campaign_id"], created["id"]),
        json=save_payload(rolls, bonus_choice=choice),
        headers=auth(world["players"][0][0]),
    )
    assert response.status_code == 422, response.text
    assert response.json().get("detail")
    character = await api_client.get(
        character_url(world["campaign_id"], created["id"]),
        headers=auth(world["players"][0][0]),
    )
    assert character.json()["version"] == 2


async def test_background_change_preserves_assignments_but_clears_incompatible_bonus(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    assigned = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert assigned.status_code == 200, assigned.text
    incompatible_background_id = await insert_background(
        database_engine,
        f"qa-incompatible-{uuid.uuid4().hex[:8]}",
        ("STR", "DEX", "CON"),
    )

    changed = await api_client.patch(
        character_url(world["campaign_id"], created["id"]),
        json={"expected_version": 3, "background_id": incompatible_background_id},
        headers=auth(player),
    )
    assert changed.status_code == 200, changed.text
    current = await api_client.get(url, headers=auth(player))
    assert current.status_code == 200
    body = current.json()
    assert body["has_rolls"] is True
    assert body["assignment_complete"] is True
    assert body["bonus_complete"] is False
    assert body["complete"] is False
    assert body["bonus_choice"] is None
    assert [item["roll_result_id"] for item in body["abilities"]] == [
        assigned.json()["abilities"][i]["roll_result_id"] for i in range(6)
    ]
    assert [item["base_value"] for item in body["abilities"]] == [
        item["base_value"] for item in assigned.json()["abilities"]
    ]
    assert all(item["bonus"] is None for item in body["abilities"])
    assert all(item["total"] is None for item in body["abilities"])
    assert all(item["modifier"] is None for item in body["abilities"])

    roll_read = await api_client.get(
        rolls_url(world["campaign_id"], created["id"]), headers=auth(player)
    )
    assert roll_read.status_code == 200
    assert roll_read.json() == rolls


async def test_legacy_character_with_null_background_can_be_read_but_not_distributed(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created = await create_character(api_client, world)
    assert created.status_code == 201, created.text
    player = world["players"][0][0]
    character_id = created.json()["id"]
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, character_id)
        assert character is not None
        character.background_id = None
        await session.commit()

    rolls = await api_client.post(
        rolls_url(world["campaign_id"], character_id), headers=auth(player)
    )
    assert rolls.status_code == 201, rolls.text
    url = distribution_url(world["campaign_id"], character_id)
    read = await api_client.get(url, headers=auth(player))
    assert read.status_code == 200, read.text
    assert read.json()["has_rolls"] is True
    assert read.json()["assignment_complete"] is False
    assert read.json()["bonus_complete"] is False
    assert read.json()["complete"] is False
    assert read.json()["bonus_choice"] is None
    assert all(item["roll_result_id"] is None for item in read.json()["abilities"])
    write = await api_client.put(
        url,
        json={
            "expected_version": 2,
            "assignments": {
                ability: result["id"]
                for ability, result in zip(
                    ABILITIES, rolls.json()["results"], strict=True
                )
            },
            "bonus_choice": plus_two_choice("INT", "WIS"),
        },
        headers=auth(player),
    )
    assert write.status_code == 409


async def test_background_patch_race_with_put_has_one_versioned_winner(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    assigned = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert assigned.status_code == 200, assigned.text
    replacement_background_id = await insert_background(
        database_engine,
        f"qa-race-{uuid.uuid4().hex[:8]}",
        ("STR", "DEX", "CON"),
    )
    barrier = asyncio.Barrier(2)

    async def save_again():
        await barrier.wait()
        return await api_client.put(
            url,
            json=save_payload(
                rolls,
                expected_version=3,
                bonus_choice=plus_two_choice("WIS", "CHA"),
            ),
            headers=auth(player),
        )

    async def change_background():
        await barrier.wait()
        return await api_client.patch(
            character_url(world["campaign_id"], created["id"]),
            json={
                "expected_version": 3,
                "background_id": replacement_background_id,
            },
            headers=auth(player),
        )

    put_response, patch_response = await asyncio.gather(
        save_again(), change_background()
    )
    assert sorted((put_response.status_code, patch_response.status_code)) == [
        200,
        409,
    ], [
        (put_response.status_code, put_response.text),
        (patch_response.status_code, patch_response.text),
    ]
    current = await api_client.get(url, headers=auth(player))
    assert current.status_code == 200
    if put_response.status_code == 200:
        assert current.json()["complete"] is True
        assert current.json()["bonus_choice"] == {
            "pattern": "plus_two_plus_one",
            "plus_two": "WIS",
            "plus_one": "CHA",
        }
    else:
        assert current.json()["complete"] is False
        assert current.json()["assignment_complete"] is True
        assert current.json()["bonus_choice"] is None


async def test_postgresql_constraints_reject_duplicate_foreign_rolls_and_null_targets(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=2)
    first_character, first_rolls = await create_rolled_character(
        api_client, database_engine, world, player_index=0
    )
    second_character, second_rolls = await create_rolled_character(
        api_client, database_engine, world, player_index=1
    )
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    result_ids = [item["id"] for item in first_rolls["results"]]
    foreign_result_id = second_rolls["results"][0]["id"]
    cases = [
        (
            "ck_ability_distributions_distinct",
            first_character["id"],
            first_rolls["id"],
            [result_ids[0], result_ids[0], *result_ids[2:]],
            "plus_two_plus_one",
            "INT",
            "WIS",
        ),
        (
            "fk_ability_distributions_str_result",
            first_character["id"],
            first_rolls["id"],
            [foreign_result_id, *result_ids[1:]],
            "plus_two_plus_one",
            "INT",
            "WIS",
        ),
        (
            "ck_ability_distributions_choice",
            first_character["id"],
            first_rolls["id"],
            result_ids,
            "plus_two_plus_one",
            None,
            "WIS",
        ),
        (
            "fk_ability_distributions_character_roll_set",
            first_character["id"],
            second_rolls["id"],
            [item["id"] for item in second_rolls["results"]],
            "plus_two_plus_one",
            "INT",
            "WIS",
        ),
    ]

    async with factory() as session:
        for (
            constraint,
            character_id,
            roll_set_id,
            ids,
            pattern,
            plus_two,
            plus_one,
        ) in cases:
            with pytest.raises(IntegrityError) as error:
                async with session.begin_nested():
                    row = AbilityDistribution(
                        character_id=character_id,
                        roll_set_id=roll_set_id,
                        str_result_id=ids[0],
                        dex_result_id=ids[1],
                        con_result_id=ids[2],
                        int_result_id=ids[3],
                        wis_result_id=ids[4],
                        cha_result_id=ids[5],
                        pattern=pattern,
                        plus_two=plus_two,
                        plus_one=plus_one,
                    )
                    session.add(row)
                    await session.flush()
            assert constraint in str(error.value.orig)
        await session.rollback()


async def test_put_requires_draft_active_campaign_and_current_version(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])

    absent = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert absent.status_code == 200
    stale = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert stale.status_code == 409

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, created["id"])
        assert character is not None
        character.status = CharacterStatus.PENDING_APPROVAL
        await session.commit()
    frozen = await api_client.put(
        url,
        json=save_payload(rolls, expected_version=3),
        headers=auth(player),
    )
    assert frozen.status_code == 409


async def test_master_can_read_but_cannot_write_and_foreign_users_get_404(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=2)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    saved = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert saved.status_code == 200, saved.text

    master_read = await api_client.get(url, headers=auth(world["master"]))
    assert master_read.status_code == 200
    assert master_read.json() == saved.json()
    master_write = await api_client.put(
        url,
        json=save_payload(rolls, expected_version=3),
        headers=auth(world["master"]),
    )
    assert master_write.status_code == 403
    other_player = await api_client.get(url, headers=auth(world["players"][1][0]))
    assert other_player.status_code == 404
    foreign_write = await api_client.put(
        url,
        json=save_payload(rolls, expected_version=3),
        headers=auth(world["players"][1][0]),
    )
    assert foreign_write.status_code == 404
    outsider, _ = await new_user(api_client, "distribution-outsider")
    assert (await api_client.get(url, headers=auth(outsider))).status_code == 404
    assert (
        await api_client.get(
            distribution_url(world["campaign_id"] + 10000, created["id"]),
            headers=auth(player),
        )
    ).status_code == 404
    assert (await api_client.get(url)).status_code == 401
    assert (await api_client.put(url, json=save_payload(rolls))).status_code == 401


async def test_background_must_allow_selected_bonus_pattern(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    unsupported_id = await insert_background(
        database_engine,
        f"qa-only-two-one-{uuid.uuid4().hex[:8]}",
        ("STR", "DEX", "CON"),
        allow_plus_two_plus_one=True,
        allow_plus_one_each=False,
    )
    player = world["players"][0][0]
    changed = await api_client.patch(
        character_url(world["campaign_id"], created["id"]),
        json={"expected_version": 2, "background_id": unsupported_id},
        headers=auth(player),
    )
    assert changed.status_code == 200, changed.text
    rejected = await api_client.put(
        distribution_url(world["campaign_id"], created["id"]),
        json=save_payload(
            rolls, expected_version=3, bonus_choice={"pattern": "plus_one_each"}
        ),
        headers=auth(player),
    )
    assert rejected.status_code == 422, rejected.text
    current = await api_client.get(
        distribution_url(world["campaign_id"], created["id"]),
        headers=auth(player),
    )
    assert current.json()["assignment_complete"] is False
    assert current.json()["complete"] is False


async def test_archived_character_and_completed_campaign_remain_readable(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    url = distribution_url(world["campaign_id"], created["id"])
    saved = await api_client.put(url, json=save_payload(rolls), headers=auth(player))
    assert saved.status_code == 200, saved.text
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = await session.get(Character, created["id"])
        campaign = await session.get(Campaign, world["campaign_id"])
        assert character is not None and campaign is not None
        character.status = CharacterStatus.ARCHIVED
        campaign.status = CampaignStatus.COMPLETED
        await session.commit()

    read = await api_client.get(url, headers=auth(player))
    assert read.status_code == 200, read.text
    assert read.json() == saved.json()
    write = await api_client.put(
        url,
        json=save_payload(rolls, expected_version=3),
        headers=auth(player),
    )
    assert write.status_code == 409


async def test_parallel_puts_use_character_version_as_compare_and_swap(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    url = distribution_url(world["campaign_id"], created["id"])
    player = world["players"][0][0]
    barrier = asyncio.Barrier(2)

    async def put(choice):
        await barrier.wait()
        return await api_client.put(
            url,
            json=save_payload(rolls, bonus_choice=choice),
            headers=auth(player),
        )

    responses = await asyncio.gather(
        put(plus_two_choice("INT", "WIS")),
        put(plus_two_choice("CHA", "INT")),
    )
    assert sorted(response.status_code for response in responses) == [200, 409], [
        (response.status_code, response.text) for response in responses
    ]
    stored = await api_client.get(url, headers=auth(player))
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    assert stored.status_code == 200
    assert stored.json() == winner


async def test_background_patch_invalidates_only_incompatible_bonus_and_keeps_rolls(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    player = world["players"][0][0]
    distribution = distribution_url(world["campaign_id"], created["id"])
    initial = await api_client.put(
        distribution,
        json=save_payload(rolls),
        headers=auth(player),
    )
    assert initial.status_code == 200, initial.text

    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    compatible_background_id = await insert_background(
        database_engine,
        f"qa-compatible-{uuid.uuid4().hex[:8]}",
        ("INT", "WIS", "CHA"),
    )
    compatible = await api_client.patch(
        character_url(world["campaign_id"], created["id"]),
        json={
            "expected_version": 3,
            "background_id": compatible_background_id,
        },
        headers=auth(player),
    )
    assert compatible.status_code == 200, compatible.text
    kept = await api_client.get(distribution, headers=auth(player))
    assert kept.status_code == 200
    assert kept.json()["bonus_complete"] is True
    assert [item["bonus"] for item in kept.json()["abilities"]] == [0, 0, 0, 2, 1, 0]
    assert (
        kept.json()["abilities"][3]["bonus_source"]["catalog_version_id"]
        == compatible_background_id
    )

    # Закрытая закреплённая версия продолжает давать свои уже сохранённые эффекты.
    async with factory() as session:
        background = await session.get(BackgroundCatalog, compatible_background_id)
        assert background is not None
        background.available_for_selection = False
        await session.commit()
    closed_rename = await api_client.patch(
        character_url(world["campaign_id"], created["id"]),
        json={"expected_version": 4, "name": "Closed version still pinned"},
        headers=auth(player),
    )
    assert closed_rename.status_code == 200, closed_rename.text
    after_rename = await api_client.get(distribution, headers=auth(player))
    assert after_rename.status_code == 200
    assert after_rename.json()["complete"] is True
    assert after_rename.json()["abilities"] == kept.json()["abilities"]


async def test_failed_distribution_write_rolls_back_everything(
    api_client, database_engine
):
    world = await setup_world(api_client, database_engine, player_count=1)
    created, rolls = await create_rolled_character(api_client, database_engine, world)
    url = distribution_url(world["campaign_id"], created["id"])
    player = world["players"][0][0]

    async with database_engine.begin() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
        assert schema and schema.startswith("qa_")
        await connection.execute(
            text(
                f'''CREATE FUNCTION "{schema}".reject_ability_distribution()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                        RAISE EXCEPTION 'forced QA distribution failure';
                    END;
                    $$'''
            )
        )
        await connection.execute(
            text(
                f'''CREATE TRIGGER qa_reject_ability_distribution
                    BEFORE INSERT OR UPDATE ON ability_distributions
                    FOR EACH ROW EXECUTE FUNCTION
                    "{schema}".reject_ability_distribution()'''
            )
        )

    transport = ASGITransport(app=api_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as failing_client:
        rejected = await failing_client.put(
            url, json=save_payload(rolls), headers=auth(player)
        )
    assert rejected.status_code == 500
    read = await api_client.get(url, headers=auth(player))
    assert read.status_code == 200
    assert read.json()["complete"] is False
    character = await api_client.get(
        character_url(world["campaign_id"], created["id"]), headers=auth(player)
    )
    assert character.json()["version"] == 2
