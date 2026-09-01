from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import InventoryPath
from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin

_ITEM_FK = "items.id"
_UOM_FK = "units_of_measure.id"
_WAREHOUSE_FK = "warehouses.id"


class UnitOfMeasure(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "units_of_measure"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    decimal_places: Mapped[int] = mapped_column(default=0, nullable=False)


class Item(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("warehouse_id", "sku"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    inventory_path: Mapped[InventoryPath] = mapped_column(
        Enum(InventoryPath, native_enum=False, length=32), nullable=False
    )
    spectrum_item_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    uom_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_UOM_FK, ondelete="RESTRICT"), nullable=False
    )
    reorder_point: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UnitConversion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "unit_conversions"
    __table_args__ = (UniqueConstraint("item_id", "from_uom_id", "to_uom_id"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_ITEM_FK, ondelete="CASCADE"), nullable=False
    )
    from_uom_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_UOM_FK, ondelete="RESTRICT"), nullable=False
    )
    to_uom_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_UOM_FK, ondelete="RESTRICT"), nullable=False
    )
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)


class ApprovedAlternate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approved_alternates"
    __table_args__ = (UniqueConstraint("item_id", "alternate_item_id"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_WAREHOUSE_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_ITEM_FK, ondelete="CASCADE"), nullable=False
    )
    alternate_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(_ITEM_FK, ondelete="CASCADE"), nullable=False
    )
