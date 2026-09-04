from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.usernames import normalize_username


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, username: str) -> str:
        return normalize_username(username)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., ge=1)
    username: str = Field(..., min_length=3, max_length=255)
    is_active: bool
    created_at: datetime
