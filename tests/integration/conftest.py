"""Opt-in PostgreSQL tests; each test owns only a freshly created UUID schema."""

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_session
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def migrate(connection: Connection, direction: str, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["connection"] = connection
    if direction == "upgrade":
        command.upgrade(config, revision)
    else:
        command.downgrade(config, revision)


@pytest.fixture
async def database_engine() -> AsyncIterator[AsyncEngine]:
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL test database")
    url = make_url(raw_url)
    if (
        os.environ.get("ALLOW_TEST_DATABASE_RESET") != "1"
        or not (url.database or "").startswith("characters_test")
        or url.drivername != "postgresql+asyncpg"
    ):
        pytest.fail("Integration DB requires explicit opt-in and characters_test* name")
    schema = "qa_" + uuid.uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    created = False
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        async with engine.begin() as connection:
            await connection.run_sync(migrate, "upgrade", "head")
        yield engine
    finally:
        await engine.dispose()
        if created:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def api_client(database_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    application = create_app()
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    application.dependency_overrides[get_session] = session_override
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client
