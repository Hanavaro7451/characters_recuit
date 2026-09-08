import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import JWTManager, PasswordHasher
from app.core.usernames import normalize_username
from app.models import User
from app.repositories.user import UserRepository

INVALID_TOKEN_DETAIL = "Не удалось подтвердить учётные данные"


class AuthService:
    """Service for autorization"""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
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

    async def login(self, username: str, password: str) -> str:
        """Login user method"""
        verify_user = await self.authenticate(username, password)
        return self.token_manager.create_access_token(verify_user.id)

    async def get_current_user(self, token: str) -> User:
        """Получить активного пользователя из access-токена."""
        try:
            payload = self.token_manager.decode_token(token)
            token_type = payload.get("type")
            subject = payload.get("sub")

            if token_type != "access" or not isinstance(subject, str):
                raise ValueError("Некорректные данные токена")

            user_id = int(subject)
            if user_id < 1:
                raise ValueError("Некорректный идентификатор пользователя")
        except (jwt.InvalidTokenError, ValueError) as error:
            raise UnauthorizedError(INVALID_TOKEN_DETAIL) from error

        user = await self.repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError(INVALID_TOKEN_DETAIL)

        return user
