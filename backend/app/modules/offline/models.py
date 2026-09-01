from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import OfflineCommandStatus
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class OfflineGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offline_grants"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_version: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OfflineCommand(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offline_commands"
    __table_args__ = (UniqueConstraint("warehouse_id", "client_command_id"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("offline_grants.id", ondelete="CASCADE"), nullable=False
    )
    client_command_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[OfflineCommandStatus] = mapped_column(
        Enum(OfflineCommandStatus, native_enum=False, length=20),
        default=OfflineCommandStatus.PENDING,
        nullable=False,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
