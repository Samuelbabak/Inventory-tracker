from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class FulfillmentBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fulfillment_batches"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="picking", nullable=False)
    handed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
