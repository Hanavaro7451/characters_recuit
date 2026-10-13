"""Load a deliberately small, immutable SRD 5.2.1 catalog snapshot."""

import asyncio
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, engine
from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog

type CatalogModel = (
    type[SpeciesCatalog] | type[ClassCatalog] | type[BackgroundCatalog]
)
type CatalogValue = str | bool

SOURCE_TITLE = "System Reference Document 5.2.1"
SOURCE_URL = "https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf"
LICENSE_NAME = "CC-BY-4.0"
ATTRIBUTION = (
    "This work includes material from the System Reference Document 5.2.1 "
    "(\u201cSRD 5.2.1\u201d) by Wizards of the Coast LLC, available at "
    "https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the "
    "Creative Commons Attribution 4.0 International License, available at "
    "https://creativecommons.org/licenses/by/4.0/legalcode."
)

COMMON = {
    "ruleset": "dnd-2024",
    "content_version": "5.2.1",
    "source_title": SOURCE_TITLE,
    "source_url": SOURCE_URL,
    "license_name": LICENSE_NAME,
    "attribution": ATTRIBUTION,
}

SEED_ENTRIES: tuple[tuple[CatalogModel, dict[str, CatalogValue]], ...] = (
    (
        SpeciesCatalog,
        {
            **COMMON,
            "code": "human",
            "name": "Human",
            "description": (
                "A humanoid species with adaptable traits described in SRD 5.2.1."
            ),
            "available_for_selection": True,
        },
    ),
    (
        ClassCatalog,
        {
            **COMMON,
            "code": "fighter",
            "name": "Fighter",
            "description": (
                "A martial class whose starting traits are described in SRD 5.2.1."
            ),
            "available_for_selection": True,
        },
    ),
    (
        BackgroundCatalog,
        {
            **COMMON,
            "code": "acolyte",
            "name": "Acolyte",
            "description": "A background shaped by service in a religious community.",
            "available_for_selection": True,
            "ability_one": "INT",
            "ability_two": "WIS",
            "ability_three": "CHA",
            "allow_plus_two_plus_one": True,
            "allow_plus_one_each": True,
        },
    ),
)


class CatalogSeedConflictError(ValueError):
    """An existing published version differs from the checked-in snapshot."""


async def seed_catalogs(session: AsyncSession) -> None:
    """Insert missing versions, preserving existing versions and availability.

    The caller owns the transaction so all three entries can be committed atomically.
    Availability is operational state: closing a version does not change its content.
    """
    for model, values in SEED_ENTRIES:
        await session.execute(
            insert(model)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["ruleset", "code", "content_version"]
            )
        )
        existing = await session.scalar(
            select(model).where(
                model.ruleset == values["ruleset"],
                model.code == values["code"],
                model.content_version == values["content_version"],
            )
        )
        if existing is None:
            raise RuntimeError(f"Catalog insert was not visible: {model.__tablename__}")
        for key, expected in values.items():
            if key == "available_for_selection":
                continue
            if getattr(existing, key) != expected:
                raise CatalogSeedConflictError(
                    f"Published catalog content differs: {model.__tablename__} "
                    f"{values['code']}@{values['content_version']} ({key})"
                )


async def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        async with async_session_factory() as session:
            async with session.begin():
                current = await session.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                if current != head:
                    raise RuntimeError(
                        "Database migrations are not at head; "
                        "run alembic upgrade head first"
                    )
                await seed_catalogs(session)
    finally:
        await engine.dispose()
    print("SRD 5.2.1 catalog seed verified")


if __name__ == "__main__":
    asyncio.run(main())
