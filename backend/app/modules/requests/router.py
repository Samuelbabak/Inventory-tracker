from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.dependencies import get_current_user, require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.requests.schemas import (
    CancelRequest,
    CreateMaterialRequest,
    MaterialRequestResponse,
    ReallocateStockRequest,
    ReallocationResponse,
    RecordPickRequest,
    SubstituteCandidateResponse,
    SubstituteAllocationRequest,
)
from app.modules.requests.service import RequestService
from app.platform.database import get_db

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("")
def list_requests(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    mine_only: Annotated[bool, Query()] = False,
) -> list[MaterialRequestResponse]:
    return RequestService(session, user).list(mine_only=mine_only)


@router.get("/{request_id}")
def get_request(
    request_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).get(request_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_request(
    payload: CreateMaterialRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.FOREMAN,
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).create(payload)


@router.post("/{request_id}/submit")
def submit_request(
    request_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.FOREMAN,
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).submit(request_id)


@router.post("/{request_id}/claim")
def claim_request(
    request_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).claim(request_id)


@router.post("/queue/claim-next")
def claim_next_request(
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse | None:
    return RequestService(session, user).claim_next()


@router.post("/reallocations")
def reallocate_stock(
    payload: ReallocateStockRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> ReallocationResponse:
    return RequestService(session, user).reallocate(
        source_allocation_id=payload.source_allocation_id,
        target_request_line_id=payload.target_request_line_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.post("/{request_id}/picks")
def record_pick(
    request_id: UUID,
    payload: RecordPickRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).record_pick(
        request_id,
        allocation_id=payload.allocation_id,
        quantity=payload.quantity,
        scanned_location_code=payload.scanned_location_code,
        scanned_sku=payload.scanned_sku,
        shortage_reason=payload.shortage_reason,
    )


@router.post("/{request_id}/substitutions")
def substitute_allocation(
    request_id: UUID,
    payload: SubstituteAllocationRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).substitute(
        request_id,
        allocation_id=payload.allocation_id,
        alternate_stock_position_id=payload.alternate_stock_position_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.get("/{request_id}/allocations/{allocation_id}/substitutes")
def list_substitute_candidates(
    request_id: UUID,
    allocation_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> list[SubstituteCandidateResponse]:
    return RequestService(session, user).list_substitute_candidates(
        request_id, allocation_id
    )


@router.post("/{request_id}/handoff")
def handoff_request(
    request_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).handoff(request_id)


@router.post("/{request_id}/cancel")
def cancel_request(
    request_id: UUID,
    payload: CancelRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, csrf=True)
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> MaterialRequestResponse:
    return RequestService(session, user).cancel(request_id, reason=payload.reason)
