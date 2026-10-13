import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.catalog_seed as catalog_seed
from app.catalog_seed import CatalogSeedConflictError, seed_catalogs
from app.domain.enums import CampaignMemberRole
from app.models import (
    BackgroundCatalog,
    Campaign,
    CampaignMember,
    Character,
    ClassCatalog,
    SpeciesCatalog,
    User,
)
from tests.integration.conftest import migrate


def species_catalog(**overrides) -> SpeciesCatalog:
    values = {
        "code": "human",
        "ruleset": "dnd-2024",
        "content_version": "srd-5.2.1",
        "name": "Human",
        "description": "A human species.",
        "source_title": "System Reference Document 5.2.1",
        "source_url": "https://example.invalid/srd",
        "license_name": "CC-BY-4.0",
        "attribution": "Test attribution",
        "available_for_selection": True,
    }
    values.update(overrides)
    return SpeciesCatalog(**values)


def class_catalog(**overrides) -> ClassCatalog:
    values = {
        "code": "fighter",
        "ruleset": "dnd-2024",
        "content_version": "srd-5.2.1",
        "name": "Fighter",
        "description": "A fighter class.",
        "source_title": "System Reference Document 5.2.1",
        "source_url": "https://example.invalid/srd",
        "license_name": "CC-BY-4.0",
        "attribution": "Test attribution",
        "available_for_selection": True,
    }
    values.update(overrides)
    return ClassCatalog(**values)


def background_catalog(**overrides) -> BackgroundCatalog:
    values = {
        "code": "acolyte",
        "ruleset": "dnd-2024",
        "content_version": "srd-5.2.1",
        "name": "Acolyte",
        "description": "An acolyte background.",
        "source_title": "System Reference Document 5.2.1",
        "source_url": "https://example.invalid/srd",
        "license_name": "CC-BY-4.0",
        "attribution": "Test attribution",
        "available_for_selection": True,
        "ability_one": "STR",
        "ability_two": "DEX",
        "ability_three": "CON",
        "allow_plus_two_plus_one": True,
        "allow_plus_one_each": True,
    }
    values.update(overrides)
    return BackgroundCatalog(**values)


async def seed_member(session) -> tuple[int, int]:
    user = User(username="catalog-owner", password_hash="unused")
    session.add(user)
    await session.flush()
    campaign = Campaign(name="catalog-campaign", created_by_id=user.id)
    session.add(campaign)
    await session.flush()
    member = CampaignMember(
        campaign_id=campaign.id,
        user_id=user.id,
        role=CampaignMemberRole.PLAYER,
    )
    session.add(member)
    await session.flush()
    return campaign.id, member.id


async def test_character_catalog_links_and_version_survive_unavailability(
    database_engine,
):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        _, member_id = await seed_member(session)
        species = species_catalog()
        character_class = class_catalog()
        background = background_catalog()
        session.add_all([species, character_class, background])
        await session.flush()
        character = Character(
            campaign_member_id=member_id,
            name="Versioned hero",
            species_id=species.id,
            class_catalog_id=character_class.id,
            background_id=background.id,
        )
        session.add(character)
        await session.commit()

        assert character.level == 1
        assert character.species_id == species.id
        assert character.class_catalog_id == character_class.id
        assert character.background_id == background.id

        species.available_for_selection = False
        await session.commit()
        character_id = character.id
        species_id = species.id

    async with factory() as session:
        saved_character = await session.get(Character, character_id)
        saved_species = await session.get(SpeciesCatalog, species_id)
        assert saved_species is not None
        assert saved_species.available_for_selection is False
        assert saved_character is not None
        assert saved_character.species_id == species_id


@pytest.mark.parametrize(
    "foreign_key",
    ["species_id", "class_catalog_id", "background_id"],
)
async def test_character_rejects_unknown_catalog_versions(database_engine, foreign_key):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        _, member_id = await seed_member(session)
        session.add(
            Character(
                campaign_member_id=member_id,
                name="Invalid reference",
                **{foreign_key: 987654321},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_character_rejects_non_positive_level(database_engine):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        _, member_id = await seed_member(session)
        session.add(
            Character(campaign_member_id=member_id, name="Invalid level", level=0)
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_database_server_default_sets_level_to_one(database_engine):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        _, member_id = await seed_member(session)
        level = await session.scalar(
            text(
                "INSERT INTO characters (campaign_member_id, status, name) "
                "VALUES (:member_id, 'DRAFT', 'Database default') RETURNING level"
            ),
            {"member_id": member_id},
        )
        assert level == 1


@pytest.mark.parametrize(
    "catalog_factory",
    [species_catalog, class_catalog, background_catalog],
)
async def test_catalog_version_identity_is_unique(database_engine, catalog_factory):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([catalog_factory(), catalog_factory()])
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.parametrize(
    "catalog_factory",
    [species_catalog, class_catalog, background_catalog],
)
async def test_used_catalog_version_cannot_be_deleted(database_engine, catalog_factory):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        _, member_id = await seed_member(session)
        catalog = catalog_factory()
        session.add(catalog)
        await session.flush()
        field = {
            SpeciesCatalog: "species_id",
            ClassCatalog: "class_catalog_id",
            BackgroundCatalog: "background_id",
        }[type(catalog)]
        session.add(
            Character(
                campaign_member_id=member_id,
                name="Pinned version",
                **{field: catalog.id},
            )
        )
        await session.commit()

        await session.delete(catalog)
        with pytest.raises(
            DBAPIError, match="Published catalog versions cannot be deleted"
        ):
            await session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"ability_two": "STR"},
        {"ability_three": "DEX"},
        {"ability_three": "BAD"},
        {"allow_plus_two_plus_one": False, "allow_plus_one_each": False},
    ],
)
async def test_background_rejects_invalid_ability_or_bonus_shape(
    database_engine, overrides
):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(background_catalog(**overrides))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.parametrize(
    "bonus_options",
    [
        {"allow_plus_two_plus_one": True, "allow_plus_one_each": False},
        {"allow_plus_two_plus_one": False, "allow_plus_one_each": True},
        {"allow_plus_two_plus_one": True, "allow_plus_one_each": True},
    ],
)
async def test_background_accepts_supported_bonus_shapes(
    database_engine, bonus_options
):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(background_catalog(**bonus_options))
        await session.commit()


async def test_upgrade_preserves_legacy_character_without_inventing_catalog_links(
    database_engine,
):
    async with database_engine.begin() as connection:
        await connection.run_sync(migrate, "downgrade", "d85fb6214e09")

        user_id = await connection.scalar(
            text(
                "INSERT INTO users (username, password_hash, is_active) "
                "VALUES ('legacy-catalog-owner', 'unused', true) RETURNING id"
            )
        )
        campaign_id = await connection.scalar(
            text(
                "INSERT INTO campaigns (name, status, invite_code, created_by_id) "
                "VALUES ('legacy-campaign', 'ACTIVE', 'legacy-invite', :user_id) "
                "RETURNING id"
            ),
            {"user_id": user_id},
        )
        member_id = await connection.scalar(
            text(
                "INSERT INTO campaign_members (campaign_id, user_id, role) "
                "VALUES (:campaign_id, :user_id, 'PLAYER') RETURNING id"
            ),
            {"campaign_id": campaign_id, "user_id": user_id},
        )
        character_id = await connection.scalar(
            text(
                "INSERT INTO characters "
                "(campaign_member_id, status, name, race, character_class) "
                "VALUES (:member_id, 'DRAFT', 'Legacy hero', 'Elf', 'Wizard') "
                "RETURNING id"
            ),
            {"member_id": member_id},
        )
        await connection.run_sync(migrate, "upgrade", "head")
        migrated = (
            await connection.execute(
                text(
                    "SELECT race, character_class, species_id, class_catalog_id, "
                    "background_id, level FROM characters WHERE id=:character_id"
                ),
                {"character_id": character_id},
            )
        ).one()

    assert migrated.race == "Elf"
    assert migrated.character_class == "Wizard"
    assert migrated.species_id is None
    assert migrated.class_catalog_id is None
    assert migrated.background_id is None
    assert migrated.level == 1


async def test_upgrade_adds_absent_legacy_columns_without_losing_other_data(
    database_engine,
):
    async with database_engine.begin() as connection:
        await connection.run_sync(migrate, "downgrade", "d85fb6214e09")
        user_id = await connection.scalar(
            text(
                "INSERT INTO users (username, password_hash, is_active) "
                "VALUES ('columnless-owner', 'unused', true) RETURNING id"
            )
        )
        campaign_id = await connection.scalar(
            text(
                "INSERT INTO campaigns (name, status, invite_code, created_by_id) "
                "VALUES ('columnless-campaign', 'ACTIVE', 'columnless-invite', "
                ":user_id) RETURNING id"
            ),
            {"user_id": user_id},
        )
        member_id = await connection.scalar(
            text(
                "INSERT INTO campaign_members (campaign_id, user_id, role) "
                "VALUES (:campaign_id, :user_id, 'PLAYER') RETURNING id"
            ),
            {"campaign_id": campaign_id, "user_id": user_id},
        )
        character_id = await connection.scalar(
            text(
                "INSERT INTO characters (campaign_member_id, status, name, race, "
                "character_class) VALUES (:member_id, 'DRAFT', 'Columnless hero', "
                "'Legacy species', 'Legacy class') RETURNING id"
            ),
            {"member_id": member_id},
        )
        await connection.execute(
            text("ALTER TABLE characters DROP COLUMN race, DROP COLUMN character_class")
        )

        await connection.run_sync(migrate, "upgrade", "head")
        migrated = (
            await connection.execute(
                text(
                    "SELECT campaign_member_id, status, name, race, character_class, "
                    "species_id, class_catalog_id, background_id, level, version "
                    "FROM characters WHERE id=:character_id"
                ),
                {"character_id": character_id},
            )
        ).one()
        counts = (
            await connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM users), "
                    "(SELECT count(*) FROM campaigns), "
                    "(SELECT count(*) FROM campaign_members), "
                    "(SELECT count(*) FROM characters)"
                )
            )
        ).one()
        await connection.run_sync(migrate, "downgrade", "d85fb6214e09")
        legacy_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("characters")
            }
        )
        preserved = (
            await connection.execute(
                text(
                    "SELECT campaign_member_id, status, name FROM characters "
                    "WHERE id=:character_id"
                ),
                {"character_id": character_id},
            )
        ).one()

    assert migrated.campaign_member_id == member_id
    assert migrated.status == "DRAFT"
    assert migrated.name == "Columnless hero"
    assert migrated.race is None
    assert migrated.character_class is None
    assert migrated.species_id is None
    assert migrated.class_catalog_id is None
    assert migrated.background_id is None
    assert migrated.level == 1
    assert migrated.version == 1
    assert counts == (1, 1, 1, 1)
    assert "race" not in legacy_columns
    assert "character_class" not in legacy_columns
    assert preserved.campaign_member_id == member_id
    assert preserved.status == "DRAFT"
    assert preserved.name == "Columnless hero"


async def test_seed_is_repeatable_without_duplicates_or_content_changes(
    database_engine,
):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    models = (SpeciesCatalog, ClassCatalog, BackgroundCatalog)

    async def snapshot(session):
        result = {}
        for model in models:
            result[model] = [
                (
                    item.id,
                    item.ruleset,
                    item.code,
                    item.content_version,
                    item.name,
                    item.description,
                    item.source_title,
                    item.source_url,
                    item.license_name,
                    item.attribution,
                    getattr(item, "ability_one", None),
                    getattr(item, "ability_two", None),
                    getattr(item, "ability_three", None),
                    getattr(item, "allow_plus_two_plus_one", None),
                    getattr(item, "allow_plus_one_each", None),
                )
                for item in (await session.scalars(select(model))).all()
            ]
        return result

    async with factory() as session:
        await seed_catalogs(session)
        await session.commit()
        before = await snapshot(session)
        await seed_catalogs(session)
        await session.commit()
        after = await snapshot(session)
    assert after == before


async def test_seed_preserves_operational_unavailability(database_engine):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        await seed_catalogs(session)
        await session.commit()
        species = await session.scalar(
            select(SpeciesCatalog).where(SpeciesCatalog.code == "human")
        )
        assert species is not None
        species.available_for_selection = False
        await session.commit()

        await seed_catalogs(session)
        await session.commit()
        assert species.available_for_selection is False


async def test_seed_conflict_rolls_back_prior_insert(database_engine, monkeypatch):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        await seed_catalogs(session)
        await session.commit()

    changed_entries = []
    for model, original in catalog_seed.SEED_ENTRIES:
        values = dict(original)
        if model is SpeciesCatalog:
            values["code"] = "temporary-before-conflict"
        elif model is ClassCatalog:
            values["description"] = "A conflicting immutable snapshot."
        changed_entries.append((model, values))
    monkeypatch.setattr(catalog_seed, "SEED_ENTRIES", tuple(changed_entries))

    async with factory() as session:
        with pytest.raises(CatalogSeedConflictError):
            await seed_catalogs(session)
        await session.rollback()
        inserted = await session.scalar(
            select(SpeciesCatalog).where(
                SpeciesCatalog.code == "temporary-before-conflict"
            )
        )
        assert inserted is None


async def test_new_catalog_version_does_not_change_existing_version(database_engine):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        await seed_catalogs(session)
        await session.commit()
        original = await session.scalar(
            select(SpeciesCatalog).where(
                SpeciesCatalog.ruleset == "dnd-2024",
                SpeciesCatalog.code == "human",
                SpeciesCatalog.content_version == "5.2.1",
            )
        )
        assert original is not None
        original_description = original.description
        session.add(
            species_catalog(
                content_version="5.2.2",
                description="A later version with separate content.",
            )
        )
        await session.commit()

        saved_original = await session.scalar(
            select(SpeciesCatalog).where(
                SpeciesCatalog.ruleset == "dnd-2024",
                SpeciesCatalog.code == "human",
                SpeciesCatalog.content_version == "5.2.1",
            )
        )
        new_version = await session.scalar(
            select(SpeciesCatalog).where(
                SpeciesCatalog.ruleset == "dnd-2024",
                SpeciesCatalog.code == "human",
                SpeciesCatalog.content_version == "5.2.2",
            )
        )
        assert saved_original is not None
        assert saved_original.description == original_description
        assert new_version is not None
        assert new_version.description == "A later version with separate content."


@pytest.mark.parametrize(
    "catalog_factory",
    [species_catalog, class_catalog, background_catalog],
)
async def test_published_catalog_immutable_fields_cannot_be_updated(
    database_engine, catalog_factory
):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        catalog = catalog_factory()
        session.add(catalog)
        await session.commit()

        catalog.description = "An attempted rewrite."
        with pytest.raises(
            DBAPIError, match="Published catalog versions cannot be changed"
        ):
            await session.commit()
        await session.rollback()


async def test_unused_catalog_version_cannot_be_deleted(database_engine):
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        catalog = species_catalog()
        session.add(catalog)
        await session.commit()
        await session.delete(catalog)
        with pytest.raises(
            DBAPIError, match="Published catalog versions cannot be deleted"
        ):
            await session.commit()
