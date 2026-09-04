from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import PasswordHasher
from app.core.usernames import normalize_username
from app.models import User
from app.repositories.user import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
        self.session = session
        self.password_hasher = PasswordHasher()

    async def register(self, username: str, password: str) -> User:
        normalized_username = normalize_username(username)
        existing_user = await self.repo.get_by_username(normalized_username)
        if existing_user:
            raise ConflictError("User with username already exists")

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
            raise ConflictError("User with username already exists") from error

        return user
