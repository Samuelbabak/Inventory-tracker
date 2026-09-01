from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import OutboxStatus
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin

_WAREHOUSE_FK = "warehouses.id"


class OutboxEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbox_events"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, native_enum=False, length=32),
        default=OutboxStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class OutboxAttempt(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbox_attempts"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="RESTRICT"), nullable=False, index=True
    )
    outbox_event_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    succeeded: Mapped[bool] = mapped_column(nullable=False)
    response_reference: Mapped[str | None] = mapped_column(String(160))
    error: Mapped[str | None] = mapped_column(Text)


class ReconciliationRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reconciliation_runs"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="RESTRICT"), nullable=False, index=True
    )
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    checked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    difference_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    differences: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
