from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings


class PasswordHasher:
    """Class for working with pass"""

    def __init__(self) -> None:
        self.password_hash = PasswordHash.recommended()

    def hash_password(self, password: str) -> str:
        return self.password_hash.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.password_hash.verify(plain_password, hashed_password)


class JWTManager:
    """Class manager for JWT tokens"""

    def __init__(self) -> None:
        self._access_token_ttl = settings.jwt_access_token_expire_minutes
        self._token_algorithm = settings.jwt_algorithm
        self._token_secret = settings.jwt_secret_key.get_secret_value()

    def create_access_token(self, user_id: int) -> str:
        """Create JWT token method"""
        expires_at = datetime.now(UTC) + timedelta(minutes=self._access_token_ttl)

        payload = {
            "sub": str(user_id),
            "type": "access",
            "exp": expires_at,
        }

        return jwt.encode(
            payload,
            self._token_secret,
            algorithm=self._token_algorithm,
        )

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode JWT token method"""
        return jwt.decode(
            token,
            self._token_secret,
            algorithms=[self._token_algorithm],
            options={
                "require": ["sub", "type", "exp"],
            },
        )
