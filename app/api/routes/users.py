from fastapi.routing import APIRouter

from app.api.deps import CurrentUserDependency, UserServiceDependency
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_profile_rt(current_user: CurrentUserDependency) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_profile_rt(
    payload: UserUpdate,
    current_user: CurrentUserDependency,
    service: UserServiceDependency,
) -> UserResponse:
    updated_user = await service.update_profile(current_user, payload.username)
    return UserResponse.model_validate(updated_user)


@router.delete("/me", response_model=UserResponse)
async def delete_profile_rt(
    current_user: CurrentUserDependency,
    service: UserServiceDependency,
) -> UserResponse:
    deleted_user = await service.delete_profile(current_user)
    return UserResponse.model_validate(deleted_user)
