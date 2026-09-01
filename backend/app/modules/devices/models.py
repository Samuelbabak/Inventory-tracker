from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Device(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("warehouse_id", "device_identifier"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    enrolled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))