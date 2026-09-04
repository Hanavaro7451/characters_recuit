from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.users import AuthService

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: SessionDependency) -> AuthService:
    return AuthService(session)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
