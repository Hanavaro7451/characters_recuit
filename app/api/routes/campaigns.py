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
