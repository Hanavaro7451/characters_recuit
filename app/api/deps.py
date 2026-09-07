from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import User
from app.services.users import AuthService

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: SessionDependency) -> AuthService:
    return AuthService(session)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    service: AuthServiceDependency,
) -> User:
    return await service.get_current_user(credentials.credentials)


CurrentUserDependency = Annotated[User, Depends(get_current_user)]
