from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification


def notify_user(
    session: Session,
    *,
    warehouse_id: UUID,
    user_id: UUID,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> Notification:
    notification = Notification(
        warehouse_id=warehouse_id,
        user_id=user_id,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(notification)
    return notification
