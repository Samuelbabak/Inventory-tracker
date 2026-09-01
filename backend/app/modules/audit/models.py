from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class AuditEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
