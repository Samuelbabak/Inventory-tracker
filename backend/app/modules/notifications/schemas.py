from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    message: str
    entity_type: str | None
    entity_id: UUID | None
    is_read: bool
    created_at: str
