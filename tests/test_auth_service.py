from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import JWTManager
from app.models import User
from app.repositories.user import UserRepository
from app.services.users import AuthService


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def token_manager() -> Mock:
    return Mock(spec=JWTManager)


@pytest.fixture
def service(
    session: AsyncMock,
    repo: AsyncMock,
    token_manager: Mock,
) -> AuthService:
    auth_service = AuthService(session)
    auth_service.repo = repo
    auth_service.token_manager = token_manager
    return auth_service


async def test_register_creates_user_with_normalized_name_and_hash(
    service: AuthService,
    session: AsyncMock,
    repo: AsyncMock,
) -> None:
    repo.get_by_username.return_value = None

    user = await service.register("Alice", "password123")

    assert user.username == "alice"
    assert user.password_hash != "password123"
    assert service.password_hasher.verify_password(
        "password123",
        user.password_hash,
    )
    repo.get_by_username.assert_awaited_once_with("alice")
    repo.create.assert_awaited_once_with(user)
    session.commit.assert_awaited_once()


async def test_register_rolls_back_after_unique_constraint_conflict(
    service: AuthService,
    session: AsyncMock,
    repo: AsyncMock,
) -> None:
    repo.get_by_username.return_value = None
    repo.create.side_effect = IntegrityError(
        "INSERT INTO users",
        {},
        Exception("unique constraint violation"),
    )

    with pytest.raises(ConflictError):
        await service.register("Alice", "password123")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_get_current_user_returns_active_user(
    service: AuthService,
    repo: AsyncMock,
    token_manager: Mock,
) -> None:
    user = User(
        id=1,
        username="alice",
        password_hash="password-hash",
        is_active=True,
    )
    token_manager.decode_token.return_value = {
        "sub": "1",
        "type": "access",
    }
    repo.get_by_id.return_value = user

    result = await service.get_current_user("access-token")

    assert result is user
    token_manager.decode_token.assert_called_once_with("access-token")
    repo.get_by_id.assert_awaited_once_with(1)


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": "1", "type": "refresh"},
        {"sub": "not-an-integer", "type": "access"},
        {"sub": None, "type": "access"},
        {"sub": "0", "type": "access"},
    ],
)
async def test_get_current_user_rejects_invalid_claims(
    service: AuthService,
    repo: AsyncMock,
    token_manager: Mock,
    payload: dict[str, object],
) -> None:
    token_manager.decode_token.return_value = payload

    with pytest.raises(UnauthorizedError):
        await service.get_current_user("access-token")

    repo.get_by_id.assert_not_awaited()


async def test_get_current_user_rejects_invalid_token(
    service: AuthService,
    repo: AsyncMock,
    token_manager: Mock,
) -> None:
    token_manager.decode_token.side_effect = jwt.InvalidTokenError

    with pytest.raises(UnauthorizedError):
        await service.get_current_user("invalid-token")

    repo.get_by_id.assert_not_awaited()


@pytest.mark.parametrize(
    "user",
    [
        None,
        User(
            id=1,
            username="alice",
            password_hash="password-hash",
            is_active=False,
        ),
    ],
)
async def test_get_current_user_rejects_unavailable_user(
    service: AuthService,
    repo: AsyncMock,
    token_manager: Mock,
    user: User | None,
) -> None:
    token_manager.decode_token.return_value = {
        "sub": "1",
        "type": "access",
    }
    repo.get_by_id.return_value = user

    with pytest.raises(UnauthorizedError):
        await service.get_current_user("access-token")
