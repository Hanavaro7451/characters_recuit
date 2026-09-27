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
    CampaignJoinRequest,
    CampaignMemberResponse,
    CampaignResponse,
)

router = APIRouter()


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
