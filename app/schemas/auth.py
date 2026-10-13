from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.usernames import normalize_username


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, username: object) -> object:
        return normalize_username(username) if isinstance(username, str) else username


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"]


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=512)
