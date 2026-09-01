from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.catalog.schemas import (
    ApprovedAlternateResponse,
    CatalogItemResponse,
    CatalogReasonRequest,
    CatalogSnapshotResponse,
    CreateApprovedAlternateRequest,
    CreateCatalogItemRequest,
    CreateUnitConversionRequest,
    CreateUnitOfMeasureRequest,
    UnitConversionResponse,
    UnitOfMeasureResponse,
    UpdateCatalogItemRequest,
)
from app.modules.catalog.service import CatalogService
from app.modules.identity.dependencies import require_roles
from app.modules.identity.service import AuthenticatedUser
from app.platform.database import get_db

router = APIRouter(prefix="/catalog", tags=["catalog administration"])

CatalogManager = Annotated[
    AuthenticatedUser,
    Depends(
        require_roles(
            Role.INVENTORY_MANAGER,
            Role.SYSTEM_ADMINISTRATOR,
            csrf=True,
        )
    ),
]


@router.get("")
def catalog_snapshot(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> CatalogSnapshotResponse:
    return CatalogService(session, user).snapshot()


@router.post("/units", status_code=status.HTTP_201_CREATED)
def create_unit(
    payload: CreateUnitOfMeasureRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> UnitOfMeasureResponse:
    return CatalogService(session, user).create_unit(payload)


@router.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(
    payload: CreateCatalogItemRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> CatalogItemResponse:
    return CatalogService(session, user).create_item(payload)


@router.put("/items/{item_id}")
def update_item(
    item_id: UUID,
    payload: UpdateCatalogItemRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> CatalogItemResponse:
    return CatalogService(session, user).update_item(item_id, payload)


@router.post("/conversions", status_code=status.HTTP_201_CREATED)
def create_conversion(
    payload: CreateUnitConversionRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> UnitConversionResponse:
    return CatalogService(session, user).create_conversion(payload)


@router.post("/alternates", status_code=status.HTTP_201_CREATED)
def approve_alternate(
    payload: CreateApprovedAlternateRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> ApprovedAlternateResponse:
    return CatalogService(session, user).approve_alternate(
        payload.item_id, payload.alternate_item_id, payload.reason
    )


@router.post("/alternates/{alternate_id}/revoke")
def revoke_alternate(
    alternate_id: UUID,
    payload: CatalogReasonRequest,
    user: CatalogManager,
    session: Annotated[Session, Depends(get_db)],
) -> ApprovedAlternateResponse:
    return CatalogService(session, user).revoke_alternate(alternate_id, payload.reason)