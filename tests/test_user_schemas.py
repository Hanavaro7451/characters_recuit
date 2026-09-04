from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.user import User
from app.schemas.user import UserCreate, UserResponse


def test_user_create_normalizes_username() -> None:
    user = UserCreate(username="Alice", password="password123")

    assert user.username == "alice"


@pytest.mark.parametrize("username", ["ali ce", " alice", "alice\t"])
def test_user_create_rejects_whitespace(username: str) -> None:
    with pytest.raises(ValidationError):
        UserCreate(username=username, password="password123")


def test_user_response_accepts_orm_model() -> None:
    user = User(
        id=1,
        username="alice",
        password_hash="secret-hash",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    response = UserResponse.model_validate(user)

    assert response.id == user.id
    assert response.username == user.username
    assert response.created_at == user.created_at
