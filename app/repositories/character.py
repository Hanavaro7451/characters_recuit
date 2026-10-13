from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import CharacterStatus
from app.models.campaign import Campaign, CampaignMember
from app.models.character import Character


class CharacterRepository:
    """Запросы персонажа с явной загрузкой связей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def membership(
        self, campaign_id: int, user_id: int, *, for_write: bool = False
    ) -> tuple[CampaignMember, Campaign] | None:
        query = (
            select(CampaignMember, Campaign)
            .join(Campaign, Campaign.id == CampaignMember.campaign_id)
            .where(Campaign.id == campaign_id, CampaignMember.user_id == user_id)
        )
        if for_write:
            query = query.with_for_update(read=True, of=Campaign)
        row = (await self.session.execute(query)).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def get(self, campaign_id: int, character_id: int) -> Character | None:
        query = (
            select(Character)
            .join(CampaignMember)
            .where(
                Character.id == character_id,
                CampaignMember.campaign_id == campaign_id,
            )
            .options(
                selectinload(Character.campaign_member),
                selectinload(Character.species),
                selectinload(Character.class_catalog),
                selectinload(Character.background),
            )
        )
        return (await self.session.scalars(query)).one_or_none()

    async def get_by_member(self, member_id: int) -> Character | None:
        query = select(Character.id).where(Character.campaign_member_id == member_id)
        character_id = (await self.session.scalars(query)).one_or_none()
        if character_id is None:
            return None
        return await self.session.get(Character, character_id)

    async def lock_for_rolls(
        self, campaign_id: int, character_id: int
    ) -> Character | None:
        """Заблокировать персонажа после блокировки кампании на чтение."""
        query = (
            select(Character)
            .join(CampaignMember)
            .where(
                Character.id == character_id,
                CampaignMember.campaign_id == campaign_id,
            )
            .with_for_update(of=Character)
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(query)).one_or_none()

    async def create(self, character: Character) -> None:
        self.session.add(character)
        await self.session.flush()

    async def update_draft(
        self,
        *,
        character_id: int,
        member_id: int,
        expected_version: int,
        changes: dict[str, str | int],
    ) -> bool:
        query = (
            update(Character)
            .where(
                Character.id == character_id,
                Character.campaign_member_id == member_id,
                Character.status == CharacterStatus.DRAFT,
                Character.version == expected_version,
            )
            .values(**changes, version=Character.version + 1, updated_at=func.now())
            .returning(Character.id)
        )
        return (await self.session.scalar(query)) is not None
