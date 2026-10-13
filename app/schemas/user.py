from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.usernames import normalize_username


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, username: object) -> object:
        return normalize_username(username) if isinstance(username, str) else username


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., ge=1)
    username: str = Field(..., min_length=3, max_length=255)
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, username: object) -> object:
        return normalize_username(username) if isinstance(username, str) else username
