from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.repositories.user import UserRepository
from app.services.users import AuthService


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def service(session: AsyncMock) -> AuthService:
    auth_service = AuthService(session)
    auth_service.repo = AsyncMock(spec=UserRepository)
    return auth_service


async def test_register_creates_user_with_normalized_name_and_hash(
    service: AuthService,
    session: AsyncMock,
) -> None:
    service.repo.get_by_username.return_value = None

    user = await service.register("Alice", "password123")

    assert user.username == "alice"
    assert user.password_hash != "password123"
    assert service.password_hasher.verify_password(
        "password123",
        user.password_hash,
    )
    service.repo.get_by_username.assert_awaited_once_with("alice")
    service.repo.create.assert_awaited_once_with(user)
    session.commit.assert_awaited_once()


async def test_register_rolls_back_after_unique_constraint_conflict(
    service: AuthService,
    session: AsyncMock,
) -> None:
    service.repo.get_by_username.return_value = None
    service.repo.create.side_effect = IntegrityError(
        "INSERT INTO users",
        {},
        Exception("unique constraint violation"),
    )

    with pytest.raises(ConflictError):
        await service.register("Alice", "password123")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
