from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: UUID
    actor_name: str
    action: str
    entity_type: str
    entity_id: UUID
    reason: str | None
    changes: dict[str, Any]
    created_at: str
