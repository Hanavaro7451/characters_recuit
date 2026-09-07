from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.usernames import normalize_username


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, username: str) -> str:
        return normalize_username(username)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
