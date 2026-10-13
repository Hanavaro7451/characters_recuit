import asyncio

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.domain.enums import ArchiveReason, CampaignMemberRole, CharacterStatus
from app.models import Campaign, CampaignMember, Character, User
from app.models.base import Base
from app.repositories.campaign import CampaignRepository
from tests.integration.conftest import migrate


async def seed(engine: AsyncEngine) -> tuple[int, int, int]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(username="alice", password_hash="not-used")
        session.add(user)
        await session.flush()
        campaign = Campaign(name="first", created_by_id=user.id)
        session.add(campaign)
        await session.flush()
        member = CampaignMember(
            campaign_id=campaign.id, user_id=user.id, role=CampaignMemberRole.PLAYER
        )
        session.add(member)
        await session.commit()
        return user.id, campaign.id, member.id


async def test_empty_upgrade_downgrade_upgrade_matches_models(database_engine) -> None:
    async with database_engine.begin() as connection:

        def check_schema(sync_connection):
            inspector = inspect(sync_connection)
            for name, table in Base.metadata.tables.items():
                actual = {column["name"] for column in inspector.get_columns(name)}
                assert actual == set(table.columns.keys()), name

        await connection.run_sync(check_schema)
        await connection.run_sync(migrate, "downgrade", "base")
        types = await connection.execute(
            text(
                "SELECT typname FROM pg_type JOIN pg_namespace n ON typnamespace=n.oid "
                "WHERE n.nspname=current_schema() AND typtype='e'"
            )
        )
        assert types.all() == []
        await connection.run_sync(migrate, "upgrade", "head")
        await connection.run_sync(check_schema)


@pytest.mark.parametrize("archived", [False, True])
async def test_character_roundtrip_and_lifetime_unique(
    database_engine, archived
) -> None:
    _, _, member_id = await seed(database_engine)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        character = Character(
            campaign_member_id=member_id,
            name="Hero",
            race="Elf",
            character_class="Wizard",
            status=CharacterStatus.ARCHIVED if archived else CharacterStatus.DRAFT,
            archive_reason=ArchiveReason.CHARACTER_DEAD if archived else None,
        )
        session.add(character)
        await session.commit()
        character_id = character.id
    async with factory() as session:
        loaded = await session.get(Character, character_id)
        assert loaded.name == "Hero"
        assert loaded.race == "Elf"
        assert loaded.character_class == "Wizard"
        session.add(
            Character(
                campaign_member_id=member_id,
                name="Replacement",
                race="Human",
                character_class="Fighter",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        assert len((await session.scalars(select(Character))).all()) == 1


async def test_membership_uniqueness_and_sql_isolation(database_engine) -> None:
    user_id, campaign_id, _ = await seed(database_engine)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        outsider = User(username="outsider", password_hash="unused")
        session.add(outsider)
        await session.flush()
        other = Campaign(name="other", created_by_id=outsider.id)
        session.add(other)
        await session.commit()
        repo = CampaignRepository(session)
        assert [c.id for c in await repo.list_by_user_id(user_id)] == [campaign_id]
        assert await repo.get_campaign_by_member(other.id, user_id) is None
        assert await repo.get_campaign_by_member(campaign_id, outsider.id) is None
        session.add(
            CampaignMember(
                campaign_id=campaign_id, user_id=user_id, role=CampaignMemberRole.PLAYER
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        assert len((await session.scalars(select(CampaignMember))).all()) == 1


async def test_concurrent_character_creation_has_one_winner(database_engine) -> None:
    _, _, member_id = await seed(database_engine)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    barrier = asyncio.Barrier(2)

    async def insert():
        async with factory() as session:
            session.add(
                Character(
                    campaign_member_id=member_id,
                    name="Hero",
                    race="Elf",
                    character_class="Wizard",
                )
            )
            await barrier.wait()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    assert sorted(await asyncio.gather(insert(), insert())) == [False, True]


async def test_concurrent_membership_creation_has_one_winner(database_engine) -> None:
    _, campaign_id, _ = await seed(database_engine)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        user = User(username="new-player", password_hash="unused")
        session.add(user)
        await session.commit()
        user_id = user.id
    barrier = asyncio.Barrier(2)

    async def insert():
        async with factory() as session:
            session.add(
                CampaignMember(
                    campaign_id=campaign_id,
                    user_id=user_id,
                    role=CampaignMemberRole.PLAYER,
                )
            )
            await barrier.wait()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    assert sorted(await asyncio.gather(insert(), insert())) == [False, True]
