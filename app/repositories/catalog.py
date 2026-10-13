from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog

CatalogType = TypeVar("CatalogType", SpeciesCatalog, ClassCatalog, BackgroundCatalog)


class CatalogRepository:
    """Чтение опубликованных версий и фиксация выбранной версии."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_available(self, model: type[CatalogType]) -> list[CatalogType]:
        query = (
            select(model)
            .where(
                model.ruleset == "dnd-2024",
                model.available_for_selection.is_(True),
            )
            .order_by(model.code, model.content_version, model.id)
        )
        return list((await self.session.scalars(query)).all())

    async def get(
        self, model: type[CatalogType], version_id: int
    ) -> CatalogType | None:
        return await self.session.get(model, version_id)

    async def lock_available(
        self, model: type[CatalogType], version_id: int
    ) -> CatalogType | None:
        query = (
            select(model)
            .where(
                model.id == version_id,
                model.ruleset == "dnd-2024",
                model.available_for_selection.is_(True),
            )
            .with_for_update(read=True)
        )
        return (await self.session.scalars(query)).one_or_none()
