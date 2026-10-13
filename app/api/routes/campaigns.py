from fastapi import status
from fastapi.routing import APIRouter

from app.api.deps import (
    CampaignMemberServiceDependency,
    CampaignServiceDependency,
    CurrentUserDependency,
)
from app.schemas.campaign import (
    CampaignCreate,
    CampaignCreatedResponse,
    CampaignInviteReadResponse,
    CampaignInviteResponse,
    CampaignJoinRequest,
    CampaignMemberResponse,
    CampaignResponse,
)

router = APIRouter()


@router.get(
    "/{campaign_id}/invite",
    response_model=CampaignInviteReadResponse,
    status_code=status.HTTP_200_OK,
)
async def get_invite(
    campaign_id: int,
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> CampaignInviteReadResponse:
    campaign = await service.get_invite_code(current_user, campaign_id)
    return CampaignInviteReadResponse.model_validate(campaign)


@router.post(
    "/",
    response_model=CampaignCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: CampaignCreate,
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> CampaignCreatedResponse:
    campaign = await service.create(payload.name, current_user)
    return CampaignCreatedResponse.model_validate(campaign)


@router.post(
    "/{campaign_id}/invite/rotate",
    response_model=CampaignInviteResponse,
    status_code=status.HTTP_200_OK,
)
async def update_invite(
    campaign_id: int,
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> CampaignInviteResponse:
    campaign = await service.update_invite_code(current_user, campaign_id)
    return CampaignInviteResponse.model_validate(campaign)


@router.post(
    "/{campaign_id}/invite/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invite(
    campaign_id: int,
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> None:
    await service.revoke_invite_code(current_user, campaign_id)


@router.post(
    "/join",
    response_model=CampaignMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_campaign(
    payload: CampaignJoinRequest,
    current_user: CurrentUserDependency,
    service: CampaignMemberServiceDependency,
) -> CampaignMemberResponse:
    member = await service.create(payload.invite_code, current_user)
    return CampaignMemberResponse.model_validate(member)


@router.get(
    "/",
    response_model=list[CampaignResponse],
    status_code=status.HTTP_200_OK,
)
async def list_campaigns(
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> list[CampaignResponse]:
    campaigns = await service.list_for_user(current_user)
    return [CampaignResponse.model_validate(campaign) for campaign in campaigns]


@router.get(
    "/{campaign_id}", response_model=CampaignResponse, status_code=status.HTTP_200_OK
)
async def get_campaign_by_member(
    campaign_id: int,
    current_user: CurrentUserDependency,
    service: CampaignServiceDependency,
) -> CampaignResponse:
    campaign = await service.get_by_member(current_user, campaign_id)
    return CampaignResponse.model_validate(campaign)


@router.get(
    "/{campaign_id}/members",
    response_model=list[CampaignMemberResponse],
    status_code=status.HTTP_200_OK,
)
async def get_campaign_members(
    campaign_id: int,
    current_user: CurrentUserDependency,
    service: CampaignMemberServiceDependency,
) -> list[CampaignMemberResponse]:
    members = await service.get_list_by_campaign(campaign_id, current_user)
    return [CampaignMemberResponse.model_validate(member) for member in members]
