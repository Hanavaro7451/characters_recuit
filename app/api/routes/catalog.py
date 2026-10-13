from typing import Annotated, Literal

from fastapi import APIRouter, Path

from app.api.deps import CatalogServiceDependency, CurrentUserDependency
from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog
from app.schemas.catalog import BackgroundVersionResponse, CatalogVersionResponse

router = APIRouter()
Ruleset = Literal["dnd-2024"]
VersionId = Annotated[int, Path(gt=0)]


@router.get("/species", response_model=list[CatalogVersionResponse])
async def list_species(
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
    ruleset: Ruleset = "dnd-2024",
) -> list[CatalogVersionResponse]:
    entries = await service.list_available(SpeciesCatalog)
    return [CatalogVersionResponse.model_validate(entry) for entry in entries]


@router.get("/classes", response_model=list[CatalogVersionResponse])
async def list_classes(
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
    ruleset: Ruleset = "dnd-2024",
) -> list[CatalogVersionResponse]:
    entries = await service.list_available(ClassCatalog)
    return [CatalogVersionResponse.model_validate(entry) for entry in entries]


@router.get("/backgrounds", response_model=list[BackgroundVersionResponse])
async def list_backgrounds(
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
    ruleset: Ruleset = "dnd-2024",
) -> list[BackgroundVersionResponse]:
    entries = await service.list_available(BackgroundCatalog)
    return [BackgroundVersionResponse.model_validate(entry) for entry in entries]


@router.get("/species/{version_id}", response_model=CatalogVersionResponse)
async def get_species(
    version_id: VersionId,
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
) -> CatalogVersionResponse:
    entry = await service.get(SpeciesCatalog, version_id)
    return CatalogVersionResponse.model_validate(entry)


@router.get("/classes/{version_id}", response_model=CatalogVersionResponse)
async def get_class(
    version_id: VersionId,
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
) -> CatalogVersionResponse:
    entry = await service.get(ClassCatalog, version_id)
    return CatalogVersionResponse.model_validate(entry)


@router.get("/backgrounds/{version_id}", response_model=BackgroundVersionResponse)
async def get_background(
    version_id: VersionId,
    _user: CurrentUserDependency,
    service: CatalogServiceDependency,
) -> BackgroundVersionResponse:
    entry = await service.get(BackgroundCatalog, version_id)
    return BackgroundVersionResponse.model_validate(entry)
