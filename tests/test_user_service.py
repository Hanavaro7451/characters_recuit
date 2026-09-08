from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models import User
from app.repositories.user import UserRepository
from app.services.user import UserService


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def service(session: AsyncMock, repo: AsyncMock) -> UserService:
    user_service = UserService(session)
    user_service.repo = repo
    return user_service


@pytest.fixture
def current_user() -> User:
    return User(
        id=1,
        username="alice",
        password_hash="password-hash",
        is_active=True,
    )


async def test_update_profile_updates_normalized_username(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
) -> None:
    repo.get_by_username.return_value = None

    async def update_username(user: User, new_username: str) -> User:
        user.username = new_username
        return user

    repo.update_username.side_effect = update_username

    result = await service.update_profile(current_user, "Bob")

    assert result is current_user
    assert result.username == "bob"
    repo.get_by_username.assert_awaited_once_with("bob")
    repo.update_username.assert_awaited_once_with(current_user, "bob")
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("username", ["alice", "Alice"])
async def test_update_profile_skips_current_username(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
    username: str,
) -> None:
    result = await service.update_profile(current_user, username)

    assert result is current_user
    assert result.username == "alice"
    repo.get_by_username.assert_not_awaited()
    repo.update_username.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


async def test_update_profile_rejects_taken_username(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
) -> None:
    repo.get_by_username.return_value = User(
        id=2,
        username="bob",
        password_hash="password-hash",
        is_active=True,
    )

    with pytest.raises(ConflictError):
        await service.update_profile(current_user, "Bob")

    assert current_user.username == "alice"
    repo.get_by_username.assert_awaited_once_with("bob")
    repo.update_username.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("error_on_commit", [False, True])
async def test_update_profile_rolls_back_after_integrity_error(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
    error_on_commit: bool,
) -> None:
    repo.get_by_username.return_value = None
    error = IntegrityError(
        "UPDATE users",
        {},
        Exception("unique constraint violation"),
    )
    if error_on_commit:
        session.commit.side_effect = error
    else:
        repo.update_username.side_effect = error

    with pytest.raises(ConflictError) as exc_info:
        await service.update_profile(current_user, "Bob")

    assert exc_info.value.__cause__ is error
    repo.get_by_username.assert_awaited_once_with("bob")
    repo.update_username.assert_awaited_once_with(current_user, "bob")
    session.rollback.assert_awaited_once()
    if error_on_commit:
        session.commit.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()


async def test_delete_profile_deactivates_user(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
) -> None:
    async def deactivate(user: User) -> None:
        user.is_active = False

    repo.deactivate.side_effect = deactivate

    result = await service.delete_profile(current_user)

    assert result is current_user
    assert result.is_active is False
    repo.deactivate.assert_awaited_once_with(current_user)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("error_on_commit", [False, True])
async def test_delete_profile_rolls_back_after_integrity_error(
    service: UserService,
    session: AsyncMock,
    repo: AsyncMock,
    current_user: User,
    error_on_commit: bool,
) -> None:
    error = IntegrityError(
        "UPDATE users",
        {},
        Exception("database error"),
    )
    if error_on_commit:
        session.commit.side_effect = error
    else:
        repo.deactivate.side_effect = error

    with pytest.raises(ConflictError) as exc_info:
        await service.delete_profile(current_user)

    assert exc_info.value.__cause__ is error
    repo.deactivate.assert_awaited_once_with(current_user)
    session.rollback.assert_awaited_once()
    if error_on_commit:
        session.commit.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()
