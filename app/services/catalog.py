from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog
from app.repositories.catalog import CatalogRepository

CatalogType = TypeVar("CatalogType", SpeciesCatalog, ClassCatalog, BackgroundCatalog)


class CatalogService:
    """Открытое для авторизованных пользователей чтение справочников."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = CatalogRepository(session)

    async def list_available(self, model: type[CatalogType]) -> list[CatalogType]:
        return await self.repo.list_available(model)

    async def get(self, model: type[CatalogType], version_id: int) -> CatalogType:
        entry = await self.repo.get(model, version_id)
        if entry is None:
            raise NotFoundError("Версия справочника не найдена")
        return entry
