from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.enums import CampaignMemberRole
from app.models.campaign import CampaignMember
from app.repositories.campaign_member import CampaignMemberRepository


async def require_campaign_master(
    member_repo: CampaignMemberRepository, campaign_id: int, user_id: int
) -> CampaignMember:
    """Return the membership or raise if the user is not this campaign's master."""
    member = await member_repo.get_by_campaign_and_user(campaign_id, user_id)
    if member is None:
        raise NotFoundError("Пользователь не найден")
    if member.role != CampaignMemberRole.MASTER:
        raise ForbiddenError("Недостаточно прав доступа")
    return member
