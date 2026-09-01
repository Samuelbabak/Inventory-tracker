from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.devices.schemas import (
    DeviceResponse,
    EnrollDeviceRequest,
    RevokeDeviceRequest,
)
from app.modules.devices.service import DeviceService
from app.modules.identity.dependencies import require_roles
from app.modules.identity.service import AuthenticatedUser
from app.platform.database import get_db

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/enroll")
def enroll_device(
    payload: EnrollDeviceRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                Role.SYSTEM_ADMINISTRATOR,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> DeviceResponse:
    return DeviceService(session, user).enroll(
        payload.device_identifier, payload.display_name
    )


@router.get("")
def list_devices(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> list[DeviceResponse]:
    return DeviceService(session, user).list()


@router.post("/{device_id}/revoke")
def revoke_device(
    device_id: UUID,
    payload: RevokeDeviceRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.SYSTEM_ADMINISTRATOR, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> DeviceResponse:
    return DeviceService(session, user).revoke(device_id, payload.reason)