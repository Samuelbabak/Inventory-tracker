from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.dependencies import require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.qr.schemas import (
    CreatedQrTokenResponse,
    CreateQrTokenRequest,
    QrResolutionResponse,
    QrTokenResponse,
    ResolveQrTokenRequest,
    RevokeQrTokenRequest,
)
from app.modules.qr.service import QrService
from app.platform.database import get_db

router = APIRouter(prefix="/qr", tags=["QR labels"])


@router.get("")
def list_qr_tokens(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[QrTokenResponse]:
    return QrService(session, user).list(limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_qr_token(
    payload: CreateQrTokenRequest,
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
) -> CreatedQrTokenResponse:
    return QrService(session, user).create(
        payload.target_type, payload.target_id, payload.expires_in_hours
    )


@router.post("/resolve")
def resolve_qr_token(
    payload: ResolveQrTokenRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.EMPLOYEE,
                Role.FOREMAN,
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                Role.SYSTEM_ADMINISTRATOR,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> QrResolutionResponse:
    return QrService(session, user).resolve(payload.token)


@router.post("/{token_id}/revoke")
def revoke_qr_token(
    token_id: UUID,
    payload: RevokeQrTokenRequest,
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
) -> QrTokenResponse:
    return QrService(session, user).revoke(token_id, payload.reason)