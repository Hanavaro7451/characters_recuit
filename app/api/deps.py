from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import User
from app.services.auth import AuthService
from app.services.campaign import CampaignService
from app.services.campaign_member import CampaignMemberService
from app.services.user import UserService

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
