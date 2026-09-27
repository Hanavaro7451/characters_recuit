from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.enums import CampaignMemberRole
from app.models import CampaignMember
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign_access import require_campaign_master


async def test_require_campaign_master_returns_membership() -> None:
    repo = AsyncMock(spec=CampaignMemberRepository)
    master = CampaignMember(campaign_id=10, user_id=2, role=CampaignMemberRole.MASTER)
    repo.get_by_campaign_and_user.return_value = master

    result = await require_campaign_master(repo, campaign_id=10, user_id=2)

    assert result is master
    repo.get_by_campaign_and_user.assert_awaited_once_with(10, 2)


@pytest.mark.parametrize(
    ("role", "expected_error", "detail"),
    [
        (None, NotFoundError, "Пользователь не найден"),
        (CampaignMemberRole.PLAYER, ForbiddenError, "Недостаточно прав доступа"),
    ],
)
async def test_require_campaign_master_rejects_unauthorized_user(
    role: CampaignMemberRole | None,
    expected_error: type[NotFoundError] | type[ForbiddenError],
    detail: str,
) -> None:
    repo = AsyncMock(spec=CampaignMemberRepository)
    repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=2, role=role)
        if role is not None
        else None
    )

    with pytest.raises(expected_error) as exc_info:
        await require_campaign_master(repo, campaign_id=10, user_id=2)

    assert exc_info.value.detail == detail
    repo.get_by_campaign_and_user.assert_awaited_once_with(10, 2)
