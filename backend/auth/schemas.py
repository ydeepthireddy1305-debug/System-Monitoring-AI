from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


Role = Literal["VIEWER", "OPERATOR", "ADMIN"]


class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    email: EmailStr | None = None
    password: str = Field(
        min_length=8,
        max_length=128,
    )
    role: Role = "VIEWER"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    role: Role
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: int
    role: Role