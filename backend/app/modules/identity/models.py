from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import Role
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin

_WAREHOUSE_FK = "warehouses.id"


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("warehouse_id", "username"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RoleAssignment(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=32), nullable=False
    )


class UserSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
