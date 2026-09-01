from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.admin_service import UserAdministrationService
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import (
    AdminUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
)
from app.modules.identity.service import AuthenticatedUser
from app.platform.database import get_db

router = APIRouter(prefix="/users", tags=["user administration"])


@router.get("")
def list_users(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> list[AdminUserResponse]:
    return UserAdministrationService(session, user).list_users()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> AdminUserResponse:
    return UserAdministrationService(session, user).create(payload)


@router.put("/{user_id}")
def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> AdminUserResponse:
    return UserAdministrationService(session, user).update(user_id, payload)