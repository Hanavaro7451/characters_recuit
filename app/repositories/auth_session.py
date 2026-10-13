from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession, RefreshToken


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, auth_session: AuthSession) -> None:
        self.session.add(auth_session)
        await self.session.flush()

    async def add_refresh_token(self, token: RefreshToken) -> None:
        self.session.add(token)
        await self.session.flush()

    async def get_by_id(self, session_id: UUID) -> AuthSession | None:
        return await self.session.get(AuthSession, session_id)

    async def lock_by_refresh_hash(self, token_hash: str) -> AuthSession | None:
        # Every rotation/logout in this family locks the same session row.
        # Unknown hashes cannot select or revoke a session.
        query = (
            select(AuthSession)
            .join(RefreshToken, RefreshToken.session_id == AuthSession.id)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update(of=AuthSession)
            .execution_options(populate_existing=True)
        )
        result = await self.session.scalars(query)
        return result.one_or_none()

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        # Read after the family lock: a concurrent rotation may have consumed it.
        query = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        result = await self.session.scalars(query)
        return result.one_or_none()
