from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.enums import CampaignMemberRole
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
