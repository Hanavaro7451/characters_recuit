from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.invites import generate_invite_code
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.models.campaign import Campaign, CampaignMember
from app.models.user import User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign_access import require_campaign_master


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

    async def update_invite_code(
        self, current_user: User, campaign_id: int
    ) -> Campaign:
        await require_campaign_master(self.member_repo, campaign_id, current_user.id)

        campaign = await self.campaign_repo.get_campaign_by_member(
            campaign_id, current_user.id
        )
        if campaign is None:
            raise NotFoundError("Кампания не найдена")
        if campaign.status == CampaignStatus.COMPLETED:
            raise ConflictError("Кампания завершена")
        new_invite_code = generate_invite_code()
        try:
            await self.campaign_repo.update_invite_code(new_invite_code, campaign)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Не удалось обновить код приглашения") from error

        return campaign

    async def get_invite_code(
        self, current_user: User, campaign_id: int
    ) -> Campaign:
        await require_campaign_master(self.member_repo, campaign_id, current_user.id)
        campaign = await self.campaign_repo.get_campaign_by_member(
            campaign_id, current_user.id
        )
        if campaign is None:
            raise NotFoundError("Кампания не найдена")
        return campaign

    async def revoke_invite_code(
        self, current_user: User, campaign_id: int
    ) -> Campaign:
        await require_campaign_master(self.member_repo, campaign_id, current_user.id)

        campaign = await self.campaign_repo.get_campaign_by_member(
            campaign_id, current_user.id
        )
        if campaign is None:
            raise NotFoundError("Кампания не найдена")
        if campaign.status == CampaignStatus.COMPLETED:
            raise ConflictError("Кампания завершена")
        try:
            await self.campaign_repo.clear_invite_code(campaign)
            await self.session.commit()
        except SQLAlchemyError as error:
            await self.session.rollback()
            raise error

        return campaign

    async def list_for_user(self, current_user: User) -> list[Campaign]:
        """Return campaigns available to the current user."""
        return await self.campaign_repo.list_by_user_id(current_user.id)

    async def get_by_member(self, current_user: User, campaign_id: int) -> Campaign:
        campaign = await self.campaign_repo.get_campaign_by_member(
            campaign_id=campaign_id, user_id=current_user.id
        )
        if campaign is None:
            raise NotFoundError("Кампания не найдена")
        return campaign
