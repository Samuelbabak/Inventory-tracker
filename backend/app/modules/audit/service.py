from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent


def record_audit(
    session: Session,
    *,
    warehouse_id: UUID,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    changes: dict[str, Any],
    reason: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        reason=reason,
    )
    session.add(event)
    return event
