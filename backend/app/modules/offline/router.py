from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.dependencies import require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.offline.schemas import (
    CreateOfflineGrant,
    OfflineConflictResponse,
    OfflineGrantResponse,
    OfflineSyncResponse,
    ResolveOfflineConflict,
    SyncOfflineCommands,
)
from app.modules.offline.service import OfflineService
from app.platform.database import get_db

router = APIRouter(prefix="/offline", tags=["offline fulfillment"])


@router.get("/conflicts")
def list_offline_conflicts(
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OfflineConflictResponse]:
    return OfflineService(session, user).list_conflicts(limit)


@router.post("/conflicts/{command_id}/reject")
def reject_offline_conflict(
    command_id: UUID,
    payload: ResolveOfflineConflict,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.INVENTORY_MANAGER,
                Role.SYSTEM_ADMINISTRATOR,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> OfflineConflictResponse:
    return OfflineService(session, user).reject_conflict(command_id, payload.reason)


@router.post("/grants", status_code=status.HTTP_201_CREATED)
def create_offline_grant(
    payload: CreateOfflineGrant,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> OfflineGrantResponse:
    return OfflineService(session, user).create_grant(payload.request_id, payload.device_id)


@router.post("/sync")
def sync_offline_commands(
    payload: SyncOfflineCommands,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> OfflineSyncResponse:
    return OfflineService(session, user).sync(
        grant_id=payload.grant_id,
        device_id=payload.device_id,
        commands=payload.commands,
    )
