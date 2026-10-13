from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    JWTManager,
    PasswordHasher,
    generate_refresh_token,
    hash_refresh_token,
)
from app.core.usernames import normalize_username
from app.models import User
from app.models.auth_session import AuthSession, RefreshToken
from app.repositories.auth_session import AuthSessionRepository
from app.repositories.user import UserRepository
from app.schemas.auth import LoginResponse

INVALID_TOKEN_DETAIL = "Не удалось подтвердить учётные данные"


class AuthService:
    """Service for autorization"""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
        self.session_repo = AuthSessionRepository(session)
        self.session = session
        self.password_hasher = PasswordHasher()
        self.token_manager = JWTManager()

    async def register(self, username: str, password: str) -> User:
        """Registration method"""
        normalized_username = normalize_username(username)
        existing_user = await self.repo.get_by_username(normalized_username)
        if existing_user:
            raise ConflictError("Имя пользователя уже занято")

        password_hash = self.password_hasher.hash_password(password)
        user = User(
            username=normalized_username,
            password_hash=password_hash,
        )

        try:
            await self.repo.create(user)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Имя пользователя уже занято") from error

        return user

    async def authenticate(self, username: str, password: str) -> User:
        """Authenticate method"""
        normalized_username = normalize_username(username)
        current_user = await self.repo.get_by_username(normalized_username)
        if current_user is None:
            raise UnauthorizedError("Неверное имя пользователя или пароль")

        verify = self.password_hasher.verify_password(
            password,
            current_user.password_hash,
        )
        if not verify or not current_user.is_active:
            raise UnauthorizedError("Неверное имя пользователя или пароль")

        return current_user

    async def login(self, username: str, password: str) -> LoginResponse:
        user = await self.authenticate(username, password)
        auth_session = AuthSession(
            id=uuid4(),
            user_id=user.id,
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        try:
            await self.session_repo.create(auth_session)
            tokens = await self._issue_tokens(auth_session)
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise
        return tokens

    async def _issue_tokens(self, auth_session: AuthSession) -> LoginResponse:
        refresh_token = generate_refresh_token()
        await self.session_repo.add_refresh_token(
            RefreshToken(
                token_hash=hash_refresh_token(refresh_token),
                session_id=auth_session.id,
            )
        )
        return LoginResponse(
            access_token=self.token_manager.create_access_token(
                auth_session.user_id, auth_session.id
            ),
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def refresh(self, refresh_token: str) -> LoginResponse:
        token_hash = hash_refresh_token(refresh_token)
        try:
            auth_session = await self.session_repo.lock_by_refresh_hash(token_hash)
            now = datetime.now(UTC)
            if (
                auth_session is None
                or auth_session.revoked_at is not None
                or auth_session.expires_at <= now
            ):
                await self.session.rollback()
                raise UnauthorizedError(INVALID_TOKEN_DETAIL)

            token = await self.session_repo.get_refresh_token(token_hash)
            if token is None:
                await self.session.rollback()
                raise UnauthorizedError(INVALID_TOKEN_DETAIL)
            if token.used_at is not None:
                # Commit the revocation before reporting replay; rollback here
                # would leave the most recently issued token usable.
                auth_session.revoked_at = now
                await self.session.commit()
                raise UnauthorizedError(INVALID_TOKEN_DETAIL)

            user = await self.repo.get_by_id(auth_session.user_id)
            if user is None or not user.is_active:
                auth_session.revoked_at = now
                await self.session.commit()
                raise UnauthorizedError(INVALID_TOKEN_DETAIL)

            token.used_at = now
            tokens = await self._issue_tokens(auth_session)
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise
        return tokens

    async def logout(self, refresh_token: str) -> None:
        try:
            auth_session = await self.session_repo.lock_by_refresh_hash(
                hash_refresh_token(refresh_token)
            )
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(UTC)
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

    async def get_current_user(self, token: str) -> User:
        """Получить активного пользователя из access-токена."""
        try:
            payload = self.token_manager.decode_token(token)
            token_type = payload.get("type")
            subject = payload.get("sub")
            session_subject = payload.get("sid")

            if (
                token_type != "access"
                or not isinstance(subject, str)
                or not isinstance(session_subject, str)
            ):
                raise ValueError("Некорректные данные токена")

            user_id = int(subject)
            session_id = UUID(session_subject)
            if user_id < 1:
                raise ValueError("Некорректный идентификатор пользователя")
        except (jwt.InvalidTokenError, ValueError) as error:
            raise UnauthorizedError(INVALID_TOKEN_DETAIL) from error

        auth_session = await self.session_repo.get_by_id(session_id)
        if (
            auth_session is None
            or auth_session.user_id != user_id
            or auth_session.revoked_at is not None
            or auth_session.expires_at <= datetime.now(UTC)
        ):
            raise UnauthorizedError(INVALID_TOKEN_DETAIL)

        user = await self.repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError(INVALID_TOKEN_DETAIL)

        return user
