from fastapi import status
from fastapi.routing import APIRouter

from app.api.deps import AuthServiceDependency
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
