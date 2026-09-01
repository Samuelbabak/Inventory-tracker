from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Notification(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
