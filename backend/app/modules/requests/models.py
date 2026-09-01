from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RequestPriority, RequestState
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin

_WAREHOUSE_FK = "warehouses.id"


class MaterialRequest(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "material_requests"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    request_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    creator_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("employee_recipients.id", ondelete="RESTRICT"), nullable=False
    )
    claimed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    state: Mapped[RequestState] = mapped_column(
        Enum(RequestState, native_enum=False, length=32), default=RequestState.DRAFT, nullable=False
    )
    priority: Mapped[RequestPriority] = mapped_column(
        Enum(RequestPriority, native_enum=False, length=16),
        default=RequestPriority.NORMAL,
        nullable=False,
    )
    urgent_reason: Mapped[str | None] = mapped_column(String(500))
    job_number: Mapped[str | None] = mapped_column(String(80))
    cost_code: Mapped[str | None] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(default=1, nullable=False)


class RequestLine(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "request_lines"
    __table_args__ = (
        CheckConstraint("requested_qty > 0", name="requested_positive"),
        CheckConstraint("allocated_qty >= 0", name="allocated_nonnegative"),
        CheckConstraint("picked_qty >= 0", name="picked_nonnegative"),
        CheckConstraint("issued_qty >= 0", name="issued_nonnegative"),
        CheckConstraint("cancelled_qty >= 0", name="cancelled_nonnegative"),
        CheckConstraint("backordered_qty >= 0", name="backordered_nonnegative"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("material_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    allocated_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    picked_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    issued_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    cancelled_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    backordered_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)


class Allocation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("picked_qty >= 0", name="picked_nonnegative"),
        CheckConstraint("issued_qty >= 0", name="issued_nonnegative"),
        CheckConstraint("picked_qty <= quantity", name="picked_within_quantity"),
        CheckConstraint("issued_qty <= picked_qty", name="issued_within_picked"),
        CheckConstraint("released_qty >= 0", name="released_nonnegative"),
        CheckConstraint("issued_qty + released_qty <= quantity", name="closed_within_quantity"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    request_line_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("request_lines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_position_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("stock_positions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    picked_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    issued_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    released_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    pick_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
