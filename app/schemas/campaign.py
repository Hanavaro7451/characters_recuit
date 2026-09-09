from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.invites import INVITE_CODE_LENGTH
from app.domain.enums import CampaignMemberRole, CampaignStatus


class CampaignCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=255)
    status: CampaignStatus
    created_by_id: int = Field(..., ge=1)
    created_at: datetime


class CampaignCreatedResponse(CampaignResponse):
    invite_code: str = Field(
        ...,
        min_length=INVITE_CODE_LENGTH,
        max_length=INVITE_CODE_LENGTH,
    )


class CampaignJoinRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    invite_code: str = Field(
        ...,
        min_length=INVITE_CODE_LENGTH,
        max_length=INVITE_CODE_LENGTH,
    )


class CampaignMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., ge=1)
    campaign_id: int = Field(..., ge=1)
    user_id: int = Field(..., ge=1)
    role: CampaignMemberRole
    created_at: datetime
