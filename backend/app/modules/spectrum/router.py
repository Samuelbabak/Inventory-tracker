from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import OutboxStatus, Role
from app.domain.errors import NotFoundError
from app.modules.identity.dependencies import require_roles
from app.modules.identity.service import AuthenticatedUser
from app.modules.spectrum.adapter import create_spectrum_adapter
from app.modules.spectrum.models import OutboxEvent
from app.modules.spectrum.reconciliation import ReconciliationService
from app.modules.spectrum.schemas import (
    OutboxEventResponse,
    ReconciliationRunResponse,
    SpectrumStatusResponse,
)
from app.platform.database import get_db
from app.platform.database.base import utc_now

router = APIRouter(prefix="/integrations/spectrum", tags=["Spectrum integration"])


@router.get("/reconciliations")
def list_reconciliations(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReconciliationRunResponse]:
    adapter = create_spectrum_adapter(settings.spectrum_adapter)
    return ReconciliationService(session, user, adapter).list(limit)


@router.post("/reconciliations")
def run_reconciliation(
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
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReconciliationRunResponse:
    adapter = create_spectrum_adapter(settings.spectrum_adapter)
    return ReconciliationService(session, user, adapter).run()


@router.get("/status")
def spectrum_status(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpectrumStatusResponse:
    adapter = create_spectrum_adapter(settings.spectrum_adapter)
    counts = dict.fromkeys(OutboxStatus, 0)
    for event_status, count in session.execute(
        select(OutboxEvent.status, func.count())
        .where(OutboxEvent.warehouse_id == user.warehouse_id)
        .group_by(OutboxEvent.status)
    ).all():
        counts[event_status] = count
    return SpectrumStatusResponse(
        health=adapter.health(), capabilities=adapter.capabilities(), counts=counts
    )


@router.get("/events")
def list_outbox_events(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OutboxEventResponse]:
    events = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.warehouse_id == user.warehouse_id)
        .order_by(OutboxEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        OutboxEventResponse(
            id=event.id,
            event_type=event.event_type,
            status=event.status,
            attempt_count=event.attempt_count,
            last_error=event.last_error,
            created_at=event.created_at.isoformat(),
            processed_at=event.processed_at.isoformat() if event.processed_at else None,
        )
        for event in events
    ]


@router.post("/events/{event_id}/retry")
def retry_outbox_event(
    event_id: UUID,
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
) -> OutboxEventResponse:
    event = session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.id == event_id,
            OutboxEvent.warehouse_id == user.warehouse_id,
            OutboxEvent.status.in_((OutboxStatus.FAILED, OutboxStatus.REQUIRES_REVIEW)),
        )
        .with_for_update()
    )
    if event is None:
        raise NotFoundError("Reviewable outbox event not found")
    event.status = OutboxStatus.PENDING
    event.available_at = utc_now()
    event.last_error = None
    session.commit()
    return OutboxEventResponse(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        attempt_count=event.attempt_count,
        last_error=event.last_error,
        created_at=event.created_at.isoformat(),
        processed_at=event.processed_at.isoformat() if event.processed_at else None,
    )
