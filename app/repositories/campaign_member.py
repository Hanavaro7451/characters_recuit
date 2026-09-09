from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import CampaignMember


class CampaignMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        campaign_member: CampaignMember,
    ) -> CampaignMember:
        self.session.add(campaign_member)
        await self.session.flush()
        await self.session.refresh(campaign_member)
        return campaign_member

    async def get_by_campaign_and_user(
        self, campaign_id: int, user_id: int
    ) -> CampaignMember | None:

        query: Select[tuple[CampaignMember]] = select(CampaignMember).where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.user_id == user_id,
        )

        result = await self.session.scalars(query)
        return result.one_or_none()
