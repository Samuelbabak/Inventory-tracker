from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditEventResponse
from app.modules.identity.dependencies import require_roles
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.platform.database import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_events(
    user: Annotated[
        AuthenticatedUser,
        Depends(require_roles(Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR)),
    ],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventResponse]:
    rows = session.execute(
        select(AuditEvent, User.display_name)
        .join(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.warehouse_id == user.warehouse_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditEventResponse(
            id=event.id,
            actor_name=actor_name,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            reason=event.reason,
            changes=event.changes,
            created_at=event.created_at.isoformat(),
        )
        for event, actor_name in rows
    ]
