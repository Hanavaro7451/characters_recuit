from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_campaign_member_service,
    get_campaign_service,
    get_current_user,
)
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.main import app
from app.models import Campaign, CampaignMember, User
from app.services.campaign import CampaignService
from app.services.campaign_member import CampaignMemberService


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.fixture
def current_user() -> User:
    return User(
        id=1,
        username="alice",
        password_hash="password-hash",
        is_active=True,
    )


async def test_create_campaign_route_returns_created_campaign(
    current_user: User,
) -> None:
    service = AsyncMock(spec=CampaignService)
    campaign = Campaign(
        id=10,
        name="Dragon Hunters",
        status=CampaignStatus.ACTIVE,
        invite_code="invite1234",
        created_by_id=current_user.id,
        created_at=datetime.now(UTC),
    )
    service.create.return_value = campaign
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_campaign_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/campaigns/",
            json={"name": "  Dragon Hunters  "},
        )

    assert response.status_code == 201
    assert response.json()["invite_code"] == "invite1234"
    assert response.json()["status"] == "active"
    service.create.assert_awaited_once_with("Dragon Hunters", current_user)


async def test_join_campaign_route_returns_player_membership(
    current_user: User,
) -> None:
    service = AsyncMock(spec=CampaignMemberService)
    member = CampaignMember(
        id=20,
        campaign_id=10,
        user_id=current_user.id,
        role=CampaignMemberRole.PLAYER,
        created_at=datetime.now(UTC),
    )
    service.create.return_value = member
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_campaign_member_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/campaigns/join",
            json={"invite_code": "invite1234"},
        )

    assert response.status_code == 201
    assert response.json()["campaign_id"] == 10
    assert response.json()["role"] == "player"
    service.create.assert_awaited_once_with("invite1234", current_user)


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/campaigns/", {"name": "   "}),
        ("/api/v1/campaigns/join", {"invite_code": "short"}),
    ],
)
async def test_campaign_routes_reject_invalid_payload(
    path: str,
    payload: dict[str, str],
    current_user: User,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 422
