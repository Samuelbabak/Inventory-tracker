from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Location(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    zone: Mapped[str] = mapped_column(String(40), nullable=False)
    aisle: Mapped[str] = mapped_column(String(40), nullable=False)
    bay: Mapped[str] = mapped_column(String(40), nullable=False)
    shelf: Mapped[str] = mapped_column(String(40), nullable=False)
    position: Mapped[str] = mapped_column(String(40), nullable=False)
    pick_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_staging: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MapGridCell(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "map_grid_cells"
    __table_args__ = (UniqueConstraint("warehouse_id", "row_index", "column_index"),)

    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("locations.id", ondelete="SET NULL"), unique=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
