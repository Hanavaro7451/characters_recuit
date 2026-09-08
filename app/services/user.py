from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.usernames import normalize_username
from app.models.user import User
from app.repositories.user import UserRepository


class UserService:
    """Service for working with users"""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
        self.session = session

    async def update_profile(
        self,
        current_user: User,
        new_username: str,
    ) -> User:
        normalize_new_username = normalize_username(new_username)
        if current_user.username != normalize_new_username:
            if await self.repo.get_by_username(normalize_new_username) is not None:
                raise ConflictError("Имя пользователя уже занято")
            try:
                await self.repo.update_username(current_user, normalize_new_username)
                await self.session.commit()
            except IntegrityError as error:
                await self.session.rollback()
                raise ConflictError("Имя пользователя уже занято") from error
        return current_user

    async def delete_profile(self, current_user: User) -> User:
        try:
            await self.repo.deactivate(current_user)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Не удалось удалить профиль") from error
        return current_user
