from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import Role
from app.modules.identity.dependencies import get_current_user, require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.schemas import (
    AdjustInventoryRequest,
    GeneralUseWithdrawalRequest,
    InventoryAvailabilityRequest,
    InventoryEventResponse,
    InventoryItemResponse,
    InventoryMutationResponse,
    MoveInventoryRequest,
    ReceiveInventoryRequest,
    ReturnInventoryRequest,
)
from app.modules.inventory.service import InventoryService
from app.modules.spectrum.adapter import create_spectrum_adapter
from app.platform.database import get_db

router = APIRouter(prefix="/inventory", tags=["inventory"])


def mutation_service(
    session: Session,
    user: AuthenticatedUser,
    settings: Settings,
) -> InventoryService:
    capabilities = create_spectrum_adapter(settings.spectrum_adapter).capabilities()
    return InventoryService(session, user, capabilities)


@router.get("")
def list_inventory(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=160)] = None,
) -> list[InventoryItemResponse]:
    return InventoryService(session, user).list_inventory(search)


@router.post("/receipts")
def receive_inventory(
    payload: ReceiveInventoryRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InventoryMutationResponse:
    return mutation_service(session, user, settings).receive(
        stock_position_id=payload.stock_position_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.post("/returns")
def return_inventory(
    payload: ReturnInventoryRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InventoryMutationResponse:
    return mutation_service(session, user, settings).return_stock(
        stock_position_id=payload.stock_position_id,
        quantity=payload.quantity,
        condition=payload.condition,
        reason=payload.reason,
    )


@router.post("/general-use-withdrawals")
def general_use_withdrawal(
    payload: GeneralUseWithdrawalRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.EMPLOYEE,
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                csrf=True,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> InventoryMutationResponse:
    return InventoryService(session, user).withdraw_general_use(
        stock_position_id=payload.stock_position_id,
        recipient_id=payload.recipient_id,
        quantity=payload.quantity,
        note=payload.note,
    )


@router.post("/moves")
def move_inventory(
    payload: MoveInventoryRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> InventoryMutationResponse:
    return InventoryService(session, user).move(
        source_stock_position_id=payload.source_stock_position_id,
        destination_stock_position_id=payload.destination_stock_position_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.post("/adjustments")
def adjust_inventory(
    payload: AdjustInventoryRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InventoryMutationResponse:
    return mutation_service(session, user, settings).adjust(
        stock_position_id=payload.stock_position_id,
        counted_on_hand=payload.counted_on_hand,
        reason=payload.reason,
    )


@router.post("/quarantines")
def quarantine_inventory(
    payload: InventoryAvailabilityRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InventoryMutationResponse:
    return mutation_service(session, user, settings).quarantine(
        stock_position_id=payload.stock_position_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.post("/releases")
def release_inventory(
    payload: InventoryAvailabilityRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, csrf=True)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InventoryMutationResponse:
    return mutation_service(session, user, settings).release(
        stock_position_id=payload.stock_position_id,
        quantity=payload.quantity,
        reason=payload.reason,
    )


@router.get("/events")
def list_inventory_events(
    user: Annotated[
        AuthenticatedUser,
        Depends(
            require_roles(
                Role.WAREHOUSE_WORKER,
                Role.INVENTORY_MANAGER,
                Role.SYSTEM_ADMINISTRATOR,
            )
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[InventoryEventResponse]:
    return InventoryService(session, user).list_events(limit)
