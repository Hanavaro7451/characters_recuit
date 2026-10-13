from typing import Annotated

from fastapi import APIRouter, Body, Path, Request, Response, status

from app.api.deps import CharacterServiceDependency, CurrentUserDependency
from app.core.exceptions import UnprocessableError
from app.models.character import Character
from app.schemas.ability_distribution import (
    AbilityDistributionResponse,
    AbilityDistributionSave,
)
from app.schemas.ability_roll import AbilityRollGenerate, AbilityRollSetResponse
from app.schemas.catalog import BackgroundVersionResponse, CatalogVersionResponse
from app.schemas.character import CharacterCreate, CharacterPatch, CharacterResponse

router = APIRouter()
CampaignId = Annotated[int, Path(gt=0)]
CharacterId = Annotated[int, Path(gt=0)]
RollBody = Annotated[AbilityRollGenerate | None, Body()]


def to_response(character: Character) -> CharacterResponse:
    member = character.campaign_member
    return CharacterResponse(
        id=character.id,
        campaign_id=member.campaign_id,
        owner_user_id=member.user_id,
        name=character.name,
        status=character.status,
        archive_reason=character.archive_reason,
        level=character.level,
        version=character.version,
        species=(
            CatalogVersionResponse.model_validate(character.species)
            if character.species is not None
            else None
        ),
        character_class=(
            CatalogVersionResponse.model_validate(character.class_catalog)
            if character.class_catalog is not None
            else None
        ),
        background=(
            BackgroundVersionResponse.model_validate(character.background)
            if character.background is not None
            else None
        ),
        legacy_race=character.race,
        legacy_character_class=character.character_class,
    )


@router.post(
    "/{campaign_id}/characters",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_character(
    campaign_id: CampaignId,
    payload: CharacterCreate,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> CharacterResponse:
    character = await service.create(campaign_id, current_user, payload)
    return to_response(character)


@router.get(
    "/{campaign_id}/characters/{character_id}", response_model=CharacterResponse
)
async def get_character(
    campaign_id: CampaignId,
    character_id: CharacterId,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> CharacterResponse:
    character = await service.get(campaign_id, character_id, current_user)
    return to_response(character)


@router.patch(
    "/{campaign_id}/characters/{character_id}", response_model=CharacterResponse
)
async def patch_character(
    campaign_id: CampaignId,
    character_id: CharacterId,
    payload: CharacterPatch,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> CharacterResponse:
    character = await service.patch(campaign_id, character_id, current_user, payload)
    return to_response(character)


@router.get(
    "/{campaign_id}/characters/{character_id}/ability-rolls",
    response_model=AbilityRollSetResponse,
)
async def get_ability_rolls(
    campaign_id: CampaignId,
    character_id: CharacterId,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> AbilityRollSetResponse:
    roll_set = await service.get_ability_rolls(campaign_id, character_id, current_user)
    return AbilityRollSetResponse.from_model(roll_set)


@router.post(
    "/{campaign_id}/characters/{character_id}/ability-rolls",
    response_model=AbilityRollSetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": AbilityRollSetResponse, "description": "Сохранённый набор"}
    },
)
async def generate_ability_rolls(
    campaign_id: CampaignId,
    character_id: CharacterId,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
    response: Response,
    request: Request,
    payload: RollBody = None,
) -> AbilityRollSetResponse:
    if payload is None and await request.body():
        raise UnprocessableError("Тело запроса должно быть пустым объектом")
    roll_set, created = await service.generate_ability_rolls(
        campaign_id, character_id, current_user
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return AbilityRollSetResponse.from_model(roll_set)


@router.get(
    "/{campaign_id}/characters/{character_id}/ability-distribution",
    response_model=AbilityDistributionResponse,
)
async def get_ability_distribution(
    campaign_id: CampaignId,
    character_id: CharacterId,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> AbilityDistributionResponse:
    return await service.get_ability_distribution(
        campaign_id, character_id, current_user
    )


@router.put(
    "/{campaign_id}/characters/{character_id}/ability-distribution",
    response_model=AbilityDistributionResponse,
)
async def save_ability_distribution(
    campaign_id: CampaignId,
    character_id: CharacterId,
    payload: AbilityDistributionSave,
    current_user: CurrentUserDependency,
    service: CharacterServiceDependency,
) -> AbilityDistributionResponse:
    return await service.save_ability_distribution(
        campaign_id, character_id, current_user, payload
    )
