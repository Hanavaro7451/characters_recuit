from enum import StrEnum


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class CampaignMemberRole(StrEnum):
    MASTER = "master"
    PLAYER = "player"
