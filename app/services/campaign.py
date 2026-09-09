from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.invites import generate_invite_code
from app.domain.enums import CampaignMemberRole
from app.models.campaign import Campaign, CampaignMember
from app.models.user import User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository


class CampaignService:
    """Service for campaign management"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repo = CampaignRepository(session)
        self.member_repo = CampaignMemberRepository(session)

    async def create(self, campaign_name: str, current_user: User) -> Campaign:
        """Campaign create method"""

        campaign = Campaign(
            name=campaign_name,
            invite_code=generate_invite_code(),
            created_by_id=current_user.id,
        )

        try:
            await self.campaign_repo.create(campaign)
            master_member = CampaignMember(
                campaign_id=campaign.id,
                user_id=current_user.id,
                role=CampaignMemberRole.MASTER,
            )
            await self.member_repo.create(master_member)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Не удалось создать кампанию") from error

        return campaign
