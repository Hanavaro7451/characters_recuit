from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.models import Campaign, CampaignMember, User
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_member import CampaignMemberRepository
from app.services.campaign import CampaignService


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
) -> CampaignService:
    campaign_service = CampaignService(session)
    campaign_service.campaign_repo = campaign_repo
    campaign_service.member_repo = member_repo
    return campaign_service


@pytest.fixture
def current_user() -> User:
    return User(
        id=1,
        username="alice",
        password_hash="password-hash",
        is_active=True,
    )


async def test_create_campaign_adds_creator_as_master(
    service: CampaignService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create_campaign(campaign: Campaign) -> Campaign:
        campaign.id = 10
        return campaign

    campaign_repo.create.side_effect = create_campaign
    monkeypatch.setattr(
        "app.services.campaign.generate_invite_code",
        lambda: "invite1234",
    )

    result = await service.create("Dragon Hunters", current_user)

    assert result.name == "Dragon Hunters"
    assert result.invite_code == "invite1234"
    assert result.created_by_id == current_user.id
    campaign_repo.create.assert_awaited_once_with(result)

    member_repo.create.assert_awaited_once()
    master_member = member_repo.create.await_args.args[0]
    assert isinstance(master_member, CampaignMember)
    assert master_member.campaign_id == result.id
    assert master_member.user_id == current_user.id
    assert master_member.role == CampaignMemberRole.MASTER
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    "failure_point",
    ["campaign", "membership", "commit"],
)
async def test_create_campaign_rolls_back_after_integrity_error(
    service: CampaignService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    failure_point: str,
) -> None:
    async def create_campaign(campaign: Campaign) -> Campaign:
        campaign.id = 10
        return campaign

    campaign_repo.create.side_effect = create_campaign
    error = IntegrityError(
        "INSERT INTO campaigns",
        {},
        Exception("database error"),
    )
    if failure_point == "campaign":
        campaign_repo.create.side_effect = error
    elif failure_point == "membership":
        member_repo.create.side_effect = error
    else:
        session.commit.side_effect = error

    with pytest.raises(ConflictError) as exc_info:
        await service.create("Dragon Hunters", current_user)

    assert exc_info.value.__cause__ is error
    campaign_repo.create.assert_awaited_once()
    session.rollback.assert_awaited_once()
    if failure_point == "campaign":
        member_repo.create.assert_not_awaited()
        session.commit.assert_not_awaited()
    elif failure_point == "membership":
        member_repo.create.assert_awaited_once()
        session.commit.assert_not_awaited()
    else:
        member_repo.create.assert_awaited_once()
        session.commit.assert_awaited_once()


async def test_list_campaigns_for_user_returns_repository_result(
    service: CampaignService,
    campaign_repo: AsyncMock,
    current_user: User,
) -> None:
    campaigns = [
        Campaign(id=10, name="Dragon Hunters", created_by_id=current_user.id),
        Campaign(id=11, name="Underdark", created_by_id=2),
    ]
    campaign_repo.list_by_user_id.return_value = campaigns

    result = await service.list_for_user(current_user)

    assert result == campaigns
    campaign_repo.list_by_user_id.assert_awaited_once_with(current_user.id)


async def test_list_campaigns_for_user_returns_empty_list(
    service: CampaignService,
    campaign_repo: AsyncMock,
    current_user: User,
) -> None:
    campaign_repo.list_by_user_id.return_value = []

    result = await service.list_for_user(current_user)

    assert result == []
    campaign_repo.list_by_user_id.assert_awaited_once_with(current_user.id)


async def test_get_campaign_for_member_returns_repository_result(
    service: CampaignService,
    campaign_repo: AsyncMock,
    current_user: User,
) -> None:
    campaign = Campaign(
        id=10,
        name="Dragon Hunters",
        created_by_id=current_user.id,
    )
    campaign_repo.get_campaign_by_member.return_value = campaign

    result = await service.get_by_member(current_user, campaign.id)

    assert result is campaign
    campaign_repo.get_campaign_by_member.assert_awaited_once_with(
        campaign_id=campaign.id,
        user_id=current_user.id,
    )


async def test_get_campaign_for_member_raises_not_found(
    service: CampaignService,
    campaign_repo: AsyncMock,
    current_user: User,
) -> None:
    campaign_repo.get_campaign_by_member.return_value = None

    with pytest.raises(NotFoundError):
        await service.get_by_member(current_user, campaign_id=10)

    campaign_repo.get_campaign_by_member.assert_awaited_once_with(
        campaign_id=10,
        user_id=current_user.id,
    )


async def test_update_invite_code_allows_master(
    service: CampaignService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member_repo.get_by_campaign_and_user.return_value = CampaignMember(
        campaign_id=10, user_id=current_user.id, role=CampaignMemberRole.MASTER
    )
    campaign = Campaign(id=10, status=CampaignStatus.ACTIVE)
    campaign_repo.get_campaign_by_member.return_value = campaign
    monkeypatch.setattr(
        "app.services.campaign.generate_invite_code", lambda: "newcode123"
    )

    result = await service.update_invite_code(current_user, campaign_id=10)

    assert result is campaign
    member_repo.get_by_campaign_and_user.assert_awaited_once_with(10, current_user.id)
    campaign_repo.get_campaign_by_member.assert_awaited_once_with(10, current_user.id)
    campaign_repo.update_invite_code.assert_awaited_once_with("newcode123", campaign)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    ("role", "expected_error"),
    [(None, NotFoundError), (CampaignMemberRole.PLAYER, ForbiddenError)],
)
async def test_update_invite_code_denies_access_before_loading_campaign(
    service: CampaignService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    role: CampaignMemberRole | None,
    expected_error: type[NotFoundError] | type[ForbiddenError],
) -> None:
    member_repo.get_by_campaign_and_user.return_value = (
        CampaignMember(campaign_id=10, user_id=current_user.id, role=role)
        if role is not None
        else None
    )

    with pytest.raises(expected_error):
        await service.update_invite_code(current_user, campaign_id=10)

    member_repo.get_by_campaign_and_user.assert_awaited_once_with(10, current_user.id)
    campaign_repo.get_campaign_by_member.assert_not_awaited()
    campaign_repo.update_invite_code.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    ("campaign_status", "expected_error"),
    [(None, NotFoundError), (CampaignStatus.COMPLETED, ConflictError)],
)
async def test_update_invite_code_rejects_missing_or_completed_campaign(
    service: CampaignService,
    session: AsyncMock,
    campaign_repo: AsyncMock,
    member_repo: AsyncMock,
    current_user: User,
    campaign_status: CampaignStatus | None,
    expected_error: type[NotFoundError] | type[ConflictError],
) -> None:
    member_repo.get_by_campaign_and_user.return_value = CampaignMember(
        campaign_id=10, user_id=current_user.id, role=CampaignMemberRole.MASTER
    )
    campaign_repo.get_campaign_by_member.return_value = (
        Campaign(id=10, status=campaign_status) if campaign_status is not None else None
    )

    with pytest.raises(expected_error):
        await service.update_invite_code(current_user, campaign_id=10)

    campaign_repo.update_invite_code.assert_not_awaited()
    session.commit.assert_not_awaited()
