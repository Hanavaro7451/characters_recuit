from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.models import Campaign, CampaignMember, User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign_member import CampaignMemberService


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def campaign_repo() -> AsyncMock:
    return AsyncMock(spec=CampaignRepository)


@pytest.fixture
def member_repo() -> AsyncMock:
    return AsyncMock(spec=CampaignMemberRepository)


@pytest.fixture
def service(
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
) -> CampaignMemberService:
    member_service = CampaignMemberService(session)
    member_service.campaign_repo = campaign_repo
    member_service.member_repo = member_repo
    return member_service


@pytest.fixture
def current_user() -> User:
    return User(
        id=2,
        username="bob",
        password_hash="password-hash",
        is_active=True,
    )


@pytest.fixture
def active_campaign() -> Campaign:
    return Campaign(
        id=10,
        name="Dragon Hunters",
        status=CampaignStatus.ACTIVE,
        invite_code="invite1234",
        created_by_id=1,
    )


async def test_join_campaign_creates_player_membership(
    service: CampaignMemberService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    active_campaign: Campaign,
) -> None:
    campaign_repo.get_by_invite_code.return_value = active_campaign
    member_repo.get_by_campaign_and_user.return_value = None

    result = await service.create("invite1234", current_user)

    campaign_repo.get_by_invite_code.assert_awaited_once_with("invite1234")
    member_repo.get_by_campaign_and_user.assert_awaited_once_with(
        campaign_id=active_campaign.id,
        user_id=current_user.id,
    )
    member_repo.create.assert_awaited_once_with(result)
    assert result.campaign_id == active_campaign.id
    assert result.user_id == current_user.id
    assert result.role == CampaignMemberRole.PLAYER
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("campaign_status", [None, CampaignStatus.COMPLETED])
async def test_join_campaign_rejects_missing_or_inactive_campaign(
    service: CampaignMemberService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    campaign_status: CampaignStatus | None,
) -> None:
    campaign = None
    if campaign_status is not None:
        campaign = Campaign(
            id=10,
            name="Dragon Hunters",
            status=campaign_status,
            invite_code="invite1234",
            created_by_id=1,
        )
    campaign_repo.get_by_invite_code.return_value = campaign

    with pytest.raises(NotFoundError):
        await service.create("invite1234", current_user)

    member_repo.get_by_campaign_and_user.assert_not_awaited()
    member_repo.create.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


async def test_join_campaign_rejects_existing_membership(
    service: CampaignMemberService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    active_campaign: Campaign,
) -> None:
    existing_member = CampaignMember(
        id=1,
        campaign_id=active_campaign.id,
        user_id=current_user.id,
        role=CampaignMemberRole.MASTER,
    )
    campaign_repo.get_by_invite_code.return_value = active_campaign
    member_repo.get_by_campaign_and_user.return_value = existing_member

    with pytest.raises(ConflictError):
        await service.create("invite1234", current_user)

    member_repo.create.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("error_on_commit", [False, True])
async def test_join_campaign_rolls_back_after_integrity_error(
    service: CampaignMemberService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    active_campaign: Campaign,
    error_on_commit: bool,
) -> None:
    campaign_repo.get_by_invite_code.return_value = active_campaign
    member_repo.get_by_campaign_and_user.return_value = None
    error = IntegrityError(
        "INSERT INTO campaign_members",
        {},
        Exception("database error"),
    )
    if error_on_commit:
        session.commit.side_effect = error
    else:
        member_repo.create.side_effect = error

    with pytest.raises(ConflictError) as exc_info:
        await service.create("invite1234", current_user)

    assert exc_info.value.__cause__ is error
    member_repo.create.assert_awaited_once()
    session.rollback.assert_awaited_once()
    if error_on_commit:
        session.commit.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()
