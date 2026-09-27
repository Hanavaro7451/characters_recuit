from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_campaign_member_service, get_current_user
from app.domain.enums import CampaignMemberRole
from app.main import create_app
from app.models import CampaignMember, User
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign_member import CampaignMemberService


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (CampaignMemberRole.MASTER, 200),
        (CampaignMemberRole.PLAYER, 403),
        (None, 404),
    ],
    ids=["master", "player", "non-member"],
)
async def test_members_endpoint_enforces_access_and_serializes_list(
    role: CampaignMemberRole | None,
    expected_status: int,
) -> None:
    application = create_app()
    current_user = User(id=1, username="alice", is_active=True)
    member_repo = AsyncMock(spec=CampaignMemberRepository)
    service = CampaignMemberService(AsyncMock(spec=AsyncSession))
    service.member_repo = member_repo
    created_at = datetime(2026, 9, 27, tzinfo=UTC)
    master = CampaignMember(
        id=20,
        campaign_id=10,
        user_id=1,
        role=CampaignMemberRole.MASTER,
        created_at=created_at,
    )
    player = CampaignMember(
        id=21,
        campaign_id=10,
        user_id=2,
        role=CampaignMemberRole.PLAYER,
        created_at=created_at,
    )
    member_repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=current_user.id, role=role)
        if role is not None
        else None
    )
    member_repo.list_by_campaign_id.return_value = [master, player]
    application.dependency_overrides[get_current_user] = lambda: current_user
    application.dependency_overrides[get_campaign_member_service] = lambda: service

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/campaigns/10/members")

    assert response.status_code == expected_status
    member_repo.get_by_campaign_and_user.assert_awaited_once_with(10, current_user.id)
    if expected_status == 200:
        assert response.json() == [
            {
                "id": 20,
                "campaign_id": 10,
                "user_id": 1,
                "role": "master",
                "created_at": "2026-09-27T00:00:00Z",
            },
            {
                "id": 21,
                "campaign_id": 10,
                "user_id": 2,
                "role": "player",
                "created_at": "2026-09-27T00:00:00Z",
            },
        ]
        member_repo.list_by_campaign_id.assert_awaited_once_with(10)
    else:
        assert set(response.json()) == {"detail"}
        assert isinstance(response.json()["detail"], str)
        member_repo.list_by_campaign_id.assert_not_awaited()
