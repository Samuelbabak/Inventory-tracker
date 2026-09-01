from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    warehouse_code: str = Field(default="WH1", min_length=1, max_length=32)


class UserContextResponse(BaseModel):
    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    username: str
    display_name: str
    roles: list[Role]


class LoginResponse(BaseModel):
    user: UserContextResponse
    csrf_token: str


class AdminUserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str
    is_active: bool
    roles: list[Role]
    created_at: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    roles: list[Role] = Field(min_length=1)


class UpdateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    is_active: bool
    password: str | None = Field(default=None, min_length=8, max_length=200)
    roles: list[Role] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)
