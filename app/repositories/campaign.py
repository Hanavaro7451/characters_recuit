from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignMember


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

    async def update_invite_code(
        self, new_invite_code: str, campaign: Campaign
    ) -> None:
        campaign.invite_code = new_invite_code
        await self.session.flush()


    async def clear_invite_code(
        self, campaign: Campaign
    ) -> None:
        campaign.invite_code = None
        await self.session.flush()


    async def list_by_user_id(self, user_id: int) -> list[Campaign]:
        query: Select[tuple[Campaign]] = (
            select(Campaign)
            .join(CampaignMember, CampaignMember.campaign_id == Campaign.id)
            .where(CampaignMember.user_id == user_id)
            .order_by(Campaign.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_campaign_by_member(
        self, campaign_id: int, user_id: int
    ) -> Campaign | None:
        query: Select[tuple[Campaign]] = (
            select(Campaign)
            .join(CampaignMember, CampaignMember.campaign_id == Campaign.id)
            .where(Campaign.id == campaign_id, CampaignMember.user_id == user_id)
        )
        result = await self.session.scalars(query)
        return result.one_or_none()
