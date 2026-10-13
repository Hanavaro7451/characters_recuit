from fastapi import Response, status
from fastapi.routing import APIRouter

from app.api.deps import AuthServiceDependency
from app.schemas.auth import LoginRequest, LoginResponse, RefreshTokenRequest
from app.schemas.user import UserCreate, UserResponse

router = APIRouter()


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: UserCreate,
    service: AuthServiceDependency,
) -> UserResponse:
    user = await service.register(**payload.model_dump())
    return UserResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    service: AuthServiceDependency,
    response: Response,
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.login(**payload.model_dump())


@router.post("/refresh", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def refresh(
    payload: RefreshTokenRequest,
    service: AuthServiceDependency,
    response: Response,
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    service: AuthServiceDependency,
) -> None:
    await service.logout(payload.refresh_token)
