from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_campaign_service, get_current_user
from app.core.invites import INVITE_CODE_LENGTH
from app.db.session import get_session
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.main import create_app
from app.models import Campaign, CampaignMember, User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate, UserUpdate
from app.services.campaign import CampaignService


@pytest.mark.parametrize("error", [SQLAlchemyError(), OSError(), TimeoutError()])
async def test_readiness_reports_connection_failures(error: Exception) -> None:
    application = create_app()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = error
    application.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "database unavailable"}


async def test_readiness_does_not_hide_programming_errors() -> None:
    application = create_app()
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = RuntimeError("programming defect")
    application.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        with pytest.raises(RuntimeError, match="programming defect"):
            await client.get("/api/v1/health/ready")


@pytest.mark.parametrize("schema", [UserCreate, UserUpdate, LoginRequest])
@pytest.mark.parametrize("username", ["ß" * 128, 123, None, [], {}, True])
def test_username_rejects_invalid_canonical_length_and_types(schema, username) -> None:
    with pytest.raises(ValidationError):
        schema(username=username, password="password123")


@pytest.mark.parametrize("schema", [UserCreate, UserUpdate, LoginRequest])
def test_username_length_is_checked_after_casefold(schema) -> None:
    assert schema(username="aß", password="password123").username == "ass"
    assert schema(username="ß" * 127 + "a", password="password123").username == (
        "ss" * 127 + "a"
    )


@pytest.mark.parametrize("status", [CampaignStatus.ACTIVE, CampaignStatus.COMPLETED])
@pytest.mark.parametrize("code", ["a" * INVITE_CODE_LENGTH, None])
async def test_master_reads_invite_without_mutating_it(status, code) -> None:
    application = create_app()
    session = AsyncMock(spec=AsyncSession)
    service = CampaignService(session)
    service.campaign_repo = AsyncMock(spec=CampaignRepository)
    service.member_repo = AsyncMock(spec=CampaignMemberRepository)
    service.member_repo.get_by_campaign_and_user.return_value = CampaignMember(
        campaign_id=10, user_id=1, role=CampaignMemberRole.MASTER
    )
    campaign = Campaign(id=10, status=status, invite_code=code)
    service.campaign_repo.get_campaign_by_member.return_value = campaign
    application.dependency_overrides[get_current_user] = lambda: User(id=1)
    application.dependency_overrides[get_campaign_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        for _ in range(2):
            response = await client.get("/api/v1/campaigns/10/invite")
            assert response.status_code == 200
            assert response.json() == {"invite_code": code}
    assert campaign.invite_code == code
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()
    service.campaign_repo.update_invite_code.assert_not_awaited()
    service.campaign_repo.clear_invite_code.assert_not_awaited()


@pytest.mark.parametrize(
    ("role", "campaign_exists", "expected"),
    [
        (CampaignMemberRole.PLAYER, True, 403),
        (None, True, 404),
        (CampaignMemberRole.MASTER, False, 404),
    ],
)
async def test_invite_read_access(role, campaign_exists, expected) -> None:
    application = create_app()
    session = AsyncMock(spec=AsyncSession)
    service = CampaignService(session)
    service.member_repo = AsyncMock(spec=CampaignMemberRepository)
    service.campaign_repo = AsyncMock(spec=CampaignRepository)
    service.member_repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=1, role=role) if role else None
    )
    service.campaign_repo.get_campaign_by_member.return_value = (
        Campaign(id=10, invite_code="x" * INVITE_CODE_LENGTH)
        if campaign_exists
        else None
    )
    application.dependency_overrides[get_current_user] = lambda: User(id=1)
    application.dependency_overrides[get_campaign_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/campaigns/10/invite")
    assert response.status_code == expected
    assert "x" * INVITE_CODE_LENGTH not in response.text
    session.commit.assert_not_awaited()
    if role != CampaignMemberRole.MASTER:
        service.campaign_repo.get_campaign_by_member.assert_not_awaited()


async def test_invite_read_requires_authentication() -> None:
    application = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/campaigns/10/invite")
    assert response.status_code == 401
