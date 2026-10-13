from enum import StrEnum


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class CampaignMemberRole(StrEnum):
    MASTER = "master"
    PLAYER = "player"


class CharacterStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ArchiveReason(StrEnum):
    CHARACTER_DEAD = "character_dead"
    CAMPAIGN_COMPLETED = "campaign_completed"
