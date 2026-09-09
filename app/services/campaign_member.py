from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.models.campaign import CampaignMember
from app.models.user import User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository


class CampaignMemberService:
    """Service for campaign management"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.member_repo = CampaignMemberRepository(session)
        self.campaign_repo = CampaignRepository(session)

    async def create(
        self, campaign_invite_code: str, current_user: User
    ) -> CampaignMember:
        campaign = await self.campaign_repo.get_by_invite_code(campaign_invite_code)
        if campaign is None or campaign.status != CampaignStatus.ACTIVE:
            raise NotFoundError("Действующая кампания не найдена")
        existing_member = await self.member_repo.get_by_campaign_and_user(
            campaign_id=campaign.id,
            user_id=current_user.id,
        )
        if existing_member:
            raise ConflictError("Пользователь уже состоит в кампании")
        member = CampaignMember(
            campaign_id=campaign.id,
            user_id=current_user.id,
            role=CampaignMemberRole.PLAYER,
        )
        try:
            await self.member_repo.create(member)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Не удалось добавить игрока") from error

        return member
