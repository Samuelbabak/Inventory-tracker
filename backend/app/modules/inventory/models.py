from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import InventoryEventType
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin

_LOCATION_FK = "locations.id"


class StockPosition(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_positions"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "item_id", "location_id"),
        CheckConstraint("on_hand >= 0", name="on_hand_nonnegative"),
        CheckConstraint("quarantined_qty >= 0", name="quarantined_nonnegative"),
        CheckConstraint("quarantined_qty <= on_hand", name="quarantined_within_on_hand"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_LOCATION_FK, ondelete="RESTRICT"), nullable=False, index=True
    )
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"), nullable=False)
    quarantined_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)


class InventoryEvent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_events"

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[InventoryEventType] = mapped_column(
        Enum(InventoryEventType, native_enum=False, length=40), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recipient_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("employee_recipients.id", ondelete="RESTRICT")
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey(_LOCATION_FK, ondelete="RESTRICT")
    )
    destination_location_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey(_LOCATION_FK, ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    uom_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    source_workflow: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
