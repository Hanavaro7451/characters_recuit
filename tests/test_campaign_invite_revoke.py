from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_campaign_service, get_current_user
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.main import create_app
from app.models import Campaign, CampaignMember, User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign import CampaignService


@pytest.fixture
def service() -> CampaignService:
    service = CampaignService(AsyncMock(spec=AsyncSession))
    service.campaign_repo = AsyncMock(spec=CampaignRepository)
    service.member_repo = AsyncMock(spec=CampaignMemberRepository)
    service.member_repo.get_by_campaign_and_user.return_value = CampaignMember(
        campaign_id=10, user_id=1, role=CampaignMemberRole.MASTER
    )
    service.campaign_repo.get_campaign_by_member.return_value = Campaign(
        id=10, status=CampaignStatus.ACTIVE, invite_code="invite1234"
    )

    async def clear_code(campaign: Campaign) -> None:
        campaign.invite_code = None

    service.campaign_repo.clear_invite_code.side_effect = clear_code
    return service


@pytest.mark.parametrize("invite_code", ["invite1234", None])
async def test_repository_clears_code_without_committing(
    invite_code: str | None,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    repo = CampaignRepository(session)
    campaign = Campaign(id=10, invite_code=invite_code)

    await repo.clear_invite_code(campaign)

    assert campaign.invite_code is None
    assert campaign.id == 10
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.delete.assert_not_awaited()


async def test_revoke_allows_master_and_is_repeatable(service: CampaignService) -> None:
    user = User(id=1)
    campaign = service.campaign_repo.get_campaign_by_member.return_value

    for _ in range(2):
        result = await service.revoke_invite_code(user, 10)
        assert result is campaign
        assert result.invite_code is None

    assert service.session.commit.await_count == 2
    assert service.campaign_repo.clear_invite_code.await_count == 2
    service.member_repo.get_by_campaign_and_user.assert_awaited_with(10, 1)
    service.campaign_repo.get_campaign_by_member.assert_awaited_with(10, 1)
    service.session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    ("role", "expected_error"),
    [(None, NotFoundError), (CampaignMemberRole.PLAYER, ForbiddenError)],
)
async def test_revoke_denies_access_before_loading_campaign(
    service: CampaignService,
    role: CampaignMemberRole | None,
    expected_error: type[NotFoundError] | type[ForbiddenError],
) -> None:
    service.member_repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=1, role=role) if role else None
    )

    with pytest.raises(expected_error):
        await service.revoke_invite_code(User(id=1), 10)

    service.member_repo.get_by_campaign_and_user.assert_awaited_once_with(10, 1)
    service.campaign_repo.get_campaign_by_member.assert_not_awaited()
    service.campaign_repo.clear_invite_code.assert_not_awaited()
    service.session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("campaign_status", "expected_error"),
    [(None, NotFoundError), (CampaignStatus.COMPLETED, ConflictError)],
)
async def test_revoke_rejects_missing_or_completed_campaign(
    service: CampaignService,
    campaign_status: CampaignStatus | None,
    expected_error: type[NotFoundError] | type[ConflictError],
) -> None:
    service.campaign_repo.get_campaign_by_member.return_value = (
        Campaign(id=10, status=campaign_status, invite_code="invite1234")
        if campaign_status
        else None
    )

    with pytest.raises(expected_error):
        await service.revoke_invite_code(User(id=1), 10)

    service.campaign_repo.clear_invite_code.assert_not_awaited()
    service.session.commit.assert_not_awaited()


@pytest.mark.parametrize("failure_point", ["flush", "commit"])
@pytest.mark.parametrize("error_type", [SQLAlchemyError, IntegrityError])
async def test_revoke_rolls_back_and_preserves_database_error(
    service: CampaignService,
    failure_point: str,
    error_type: type[SQLAlchemyError],
) -> None:
    error = (
        IntegrityError("UPDATE campaigns", {}, Exception("constraint failed"))
        if error_type is IntegrityError
        else SQLAlchemyError("database failed")
    )
    if failure_point == "flush":
        service.campaign_repo.clear_invite_code.side_effect = error
    else:
        service.session.commit.side_effect = error

    with pytest.raises(SQLAlchemyError) as exc_info:
        await service.revoke_invite_code(User(id=1), 10)

    assert exc_info.value is error
    service.session.rollback.assert_awaited_once()
    if failure_point == "flush":
        service.session.commit.assert_not_awaited()


@pytest.mark.parametrize("invite_code", ["invite1234", None])
async def test_revoke_endpoint_returns_204_with_empty_body(
    service: CampaignService, invite_code: str | None
) -> None:
    application = create_app()
    service.campaign_repo.get_campaign_by_member.return_value.invite_code = invite_code
    application.dependency_overrides[get_current_user] = lambda: User(id=1)
    application.dependency_overrides[get_campaign_service] = lambda: service
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/campaigns/10/invite/revoke")

    assert response.status_code == 204
    assert response.content == b""
    service.session.commit.assert_awaited_once()
    service.campaign_repo.clear_invite_code.assert_awaited_once()


@pytest.mark.parametrize(
    ("role", "campaign_status", "expected_status"),
    [
        (CampaignMemberRole.PLAYER, CampaignStatus.ACTIVE, 403),
        (None, CampaignStatus.ACTIVE, 404),
        (CampaignMemberRole.MASTER, CampaignStatus.COMPLETED, 409),
        (CampaignMemberRole.MASTER, None, 404),
    ],
)
async def test_revoke_endpoint_rejects_invalid_access_or_campaign(
    service: CampaignService,
    role: CampaignMemberRole | None,
    campaign_status: CampaignStatus | None,
    expected_status: int,
) -> None:
    application = create_app()
    service.member_repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=1, role=role) if role else None
    )
    service.campaign_repo.get_campaign_by_member.return_value = (
        Campaign(id=10, status=campaign_status) if campaign_status else None
    )
    application.dependency_overrides[get_current_user] = lambda: User(id=1)
    application.dependency_overrides[get_campaign_service] = lambda: service
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/campaigns/10/invite/revoke")

    assert response.status_code == expected_status
    assert isinstance(response.json()["detail"], str)
    service.campaign_repo.clear_invite_code.assert_not_awaited()
    service.session.commit.assert_not_awaited()


async def test_revoke_endpoint_requires_authentication(
    service: CampaignService,
) -> None:
    application = create_app()
    application.dependency_overrides[get_campaign_service] = lambda: service
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/campaigns/10/invite/revoke")

    assert response.status_code == 401
    service.member_repo.get_by_campaign_and_user.assert_not_awaited()
    service.session.commit.assert_not_awaited()


async def test_revoke_endpoint_does_not_disguise_database_error_as_conflict(
    service: CampaignService,
) -> None:
    application = create_app()
    application.debug = False
    service.session.commit.side_effect = SQLAlchemyError("database failed")
    application.dependency_overrides[get_current_user] = lambda: User(id=1)
    application.dependency_overrides[get_campaign_service] = lambda: service
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/campaigns/10/invite/revoke")

    assert response.status_code == 500
    assert "database failed" not in response.text
    service.session.rollback.assert_awaited_once()
