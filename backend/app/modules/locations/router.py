from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.dependencies import get_current_user, require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.locations.schemas import (
    CreateLocationRequest,
    LocationResponse,
    UpdateLocationRequest,
)
from app.modules.locations.service import LocationService
from app.platform.database import get_db

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
def list_locations(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[LocationResponse]:
    return LocationService(session, user).list()


@router.post("")
def create_location(
    payload: CreateLocationRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> LocationResponse:
    return LocationService(session, user).create(payload)


@router.put("/{location_id}")
def update_location(
    location_id: UUID,
    payload: UpdateLocationRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> LocationResponse:
    return LocationService(session, user).update(location_id, payload)
