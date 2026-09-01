from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import ConflictError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.identity.service import AuthenticatedUser
from app.modules.locations.models import Location, MapGridCell
from app.modules.locations.schemas import (
    CreateLocationRequest,
    LocationResponse,
    UpdateLocationRequest,
)


class LocationService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def list(self) -> list[LocationResponse]:
        rows = self.session.execute(
            select(Location, MapGridCell)
            .outerjoin(MapGridCell, MapGridCell.location_id == Location.id)
            .where(Location.warehouse_id == self.user.warehouse_id)
            .order_by(Location.pick_sequence)
        ).all()
        return [self._response(location, cell) for location, cell in rows]

    def create(self, payload: CreateLocationRequest) -> LocationResponse:
        code = payload.code.strip().upper()
        self._assert_code_available(code)
        location = Location(
            warehouse_id=self.user.warehouse_id,
            code=code,
            zone=payload.zone.strip().upper(),
            aisle=payload.aisle.strip().upper(),
            bay=payload.bay.strip().upper(),
            shelf=payload.shelf.strip().upper(),
            position=payload.position.strip().upper(),
            pick_sequence=payload.pick_sequence,
            is_staging=payload.is_staging,
        )
        self.session.add(location)
        self.session.flush()
        cell = self._save_grid_cell(
            location, payload.grid_row, payload.grid_column
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="location.created",
            entity_type="location",
            entity_id=location.id,
            changes={
                "code": location.code,
                "grid_row": payload.grid_row,
                "grid_column": payload.grid_column,
            },
        )
        self.session.commit()
        return self._response(location, cell)

    def update(
        self, location_id: UUID, payload: UpdateLocationRequest
    ) -> LocationResponse:
        location = self.session.scalar(
            select(Location)
            .where(
                Location.id == location_id,
                Location.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if location is None:
            raise NotFoundError("Location not found")
        code = payload.code.strip().upper()
        self._assert_code_available(code, exclude_id=location.id)
        previous = {
            "code": location.code,
            "zone": location.zone,
            "aisle": location.aisle,
            "bay": location.bay,
            "shelf": location.shelf,
            "position": location.position,
            "pick_sequence": location.pick_sequence,
            "is_staging": location.is_staging,
        }
        location.code = code
        location.zone = payload.zone.strip().upper()
        location.aisle = payload.aisle.strip().upper()
        location.bay = payload.bay.strip().upper()
        location.shelf = payload.shelf.strip().upper()
        location.position = payload.position.strip().upper()
        location.pick_sequence = payload.pick_sequence
        location.is_staging = payload.is_staging
        cell = self._save_grid_cell(
            location, payload.grid_row, payload.grid_column
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="location.updated",
            entity_type="location",
            entity_id=location.id,
            changes={
                "before": previous,
                "after": {
                    "code": location.code,
                    "zone": location.zone,
                    "aisle": location.aisle,
                    "bay": location.bay,
                    "shelf": location.shelf,
                    "position": location.position,
                    "pick_sequence": location.pick_sequence,
                    "is_staging": location.is_staging,
                    "grid_row": payload.grid_row,
                    "grid_column": payload.grid_column,
                },
            },
            reason=payload.reason,
        )
        self.session.commit()
        return self._response(location, cell)

    def _save_grid_cell(
        self,
        location: Location,
        row_index: int | None,
        column_index: int | None,
    ) -> MapGridCell | None:
        cell = self.session.scalar(
            select(MapGridCell).where(MapGridCell.location_id == location.id)
        )
        if row_index is None or column_index is None:
            if cell is not None:
                self.session.delete(cell)
            return None
        collision = self.session.scalar(
            select(MapGridCell.id).where(
                MapGridCell.warehouse_id == self.user.warehouse_id,
                MapGridCell.row_index == row_index,
                MapGridCell.column_index == column_index,
                MapGridCell.location_id != location.id,
            )
        )
        if collision:
            raise ConflictError("Warehouse grid cell is already occupied")
        if cell is None:
            cell = MapGridCell(
                warehouse_id=self.user.warehouse_id,
                location_id=location.id,
                row_index=row_index,
                column_index=column_index,
                label=location.code,
            )
            self.session.add(cell)
        else:
            cell.row_index = row_index
            cell.column_index = column_index
            cell.label = location.code
        return cell

    def _assert_code_available(
        self, code: str, exclude_id: UUID | None = None
    ) -> None:
        query = select(Location.id).where(
            Location.warehouse_id == self.user.warehouse_id,
            Location.code == code,
        )
        if exclude_id is not None:
            query = query.where(Location.id != exclude_id)
        if self.session.scalar(query):
            raise ConflictError("Location code already exists")

    @staticmethod
    def _response(
        location: Location, cell: MapGridCell | None
    ) -> LocationResponse:
        return LocationResponse(
            id=location.id,
            code=location.code,
            zone=location.zone,
            aisle=location.aisle,
            bay=location.bay,
            shelf=location.shelf,
            position=location.position,
            pick_sequence=location.pick_sequence,
            is_staging=location.is_staging,
            grid_row=cell.row_index if cell else None,
            grid_column=cell.column_index if cell else None,
        )