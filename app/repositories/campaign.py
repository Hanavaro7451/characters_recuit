from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, campaign: Campaign) -> Campaign:
        self.session.add(campaign)
        await self.session.flush()
        await self.session.refresh(campaign)
        return campaign

    async def get_by_invite_code(self, invite_code: str) -> Campaign | None:
        query: Select[tuple[Campaign]] = select(Campaign).where(
            Campaign.invite_code == invite_code
        )
        result = await self.session.scalars(query)
        return result.one_or_none()
