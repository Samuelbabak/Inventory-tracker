from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.modules.identity.dependencies import get_csrf_user, get_current_user
from app.modules.identity.service import AuthenticatedUser
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationResponse
from app.platform.database import get_db
from app.platform.database.base import utc_now

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        message=notification.message,
        entity_type=notification.entity_type,
        entity_id=notification.entity_id,
        is_read=notification.read_at is not None,
        created_at=notification.created_at.isoformat(),
    )


@router.get("")
def list_notifications(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[NotificationResponse]:
    notifications = session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    ).all()
    return [_response(notification) for notification in notifications]


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notification_read(
    notification_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_csrf_user)],
    session: Annotated[Session, Depends(get_db)],
) -> None:
    notification = session.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .with_for_update()
    )
    if notification is None:
        raise NotFoundError("Notification not found")
    notification.read_at = utc_now()
    session.commit()
