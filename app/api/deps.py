from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.db.session import get_session
from app.models import User
from app.services.auth import AuthService
from app.services.campaign import CampaignService
from app.services.campaign_member import CampaignMemberService
from app.services.catalog import CatalogService
from app.services.character import CharacterService
from app.services.user import UserService

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: SessionDependency) -> AuthService:
    return AuthService(session)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    service: AuthServiceDependency,
) -> User:
    if credentials is None:
        raise UnauthorizedError("Требуется авторизация")
    return await service.get_current_user(credentials.credentials)


CurrentUserDependency = Annotated[User, Depends(get_current_user)]


def get_user_service(session: SessionDependency) -> UserService:
    return UserService(session)


UserServiceDependency = Annotated[UserService, Depends(get_user_service)]


def get_campaign_service(session: SessionDependency) -> CampaignService:
    return CampaignService(session)


CampaignServiceDependency = Annotated[
    CampaignService,
    Depends(get_campaign_service),
]


def get_campaign_member_service(
    session: SessionDependency,
) -> CampaignMemberService:
    return CampaignMemberService(session)


CampaignMemberServiceDependency = Annotated[
    CampaignMemberService,
    Depends(get_campaign_member_service),
]


def get_catalog_service(session: SessionDependency) -> CatalogService:
    return CatalogService(session)


CatalogServiceDependency = Annotated[CatalogService, Depends(get_catalog_service)]


def get_character_service(session: SessionDependency) -> CharacterService:
    return CharacterService(session)


CharacterServiceDependency = Annotated[
    CharacterService, Depends(get_character_service)
]
