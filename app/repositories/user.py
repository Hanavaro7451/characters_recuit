from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_username(self, username: str) -> User | None:
        query: Select[tuple[User]] = select(User).where(User.username == username)
        result = await self.session.scalars(query)
        return result.one_or_none()
