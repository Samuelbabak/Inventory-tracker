from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.domain.enums import InventoryEventType, InventoryPath, RequestState, Role
from app.domain.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.audit.service import record_audit
from app.modules.catalog.models import Item, UnitOfMeasure
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.domain import StockSummary
from app.modules.inventory.models import InventoryEvent, StockPosition
from app.modules.inventory.schemas import (
    InventoryEventResponse,
    InventoryItemResponse,
    InventoryMutationResponse,
    StockLocationResponse,
)
from app.modules.locations.models import Location
from app.modules.recipients.models import EmployeeRecipient
from app.modules.requests.models import Allocation, MaterialRequest, RequestLine

OPEN_REQUEST_STATES = (
    RequestState.SUBMITTED,
    RequestState.CLAIMED,
    RequestState.IN_PROGRESS,
    RequestState.READY,
    RequestState.PARTIALLY_FULFILLED,
    RequestState.ON_HOLD,
)


class InventoryService:
    def __init__(
        self,
        session: Session,
        user: AuthenticatedUser,
        spectrum_capabilities: dict[str, bool] | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.spectrum_capabilities = spectrum_capabilities or {}

    def list_inventory(self, search: str | None = None) -> list[InventoryItemResponse]:
        item_query = (
            select(Item, UnitOfMeasure.code)
            .join(UnitOfMeasure, UnitOfMeasure.id == Item.uom_id)
            .where(Item.warehouse_id == self.user.warehouse_id, Item.is_active.is_(True))
            .order_by(Item.description)
        )
        if search:
            pattern = f"%{search.strip()}%"
            location_match = (
                select(StockPosition.id)
                .join(Location, Location.id == StockPosition.location_id)
                .where(
                    StockPosition.item_id == Item.id,
                    StockPosition.warehouse_id == self.user.warehouse_id,
                    Location.code.ilike(pattern),
                )
                .exists()
            )
            item_query = item_query.where(
                or_(
                    Item.sku.ilike(pattern),
                    Item.description.ilike(pattern),
                    location_match,
                )
            )
        item_rows = self.session.execute(item_query).all()
        item_ids = [item.id for item, _ in item_rows]
        if not item_ids:
            return []

        position_rows = self.session.execute(
            select(StockPosition, Location)
            .join(Location, Location.id == StockPosition.location_id)
            .where(
                StockPosition.warehouse_id == self.user.warehouse_id,
                StockPosition.item_id.in_(item_ids),
            )
            .order_by(Location.pick_sequence)
        ).all()
        positions_by_item: dict[UUID, list[tuple[StockPosition, Location]]] = defaultdict(list)
        for position, location in position_rows:
            positions_by_item[position.item_id].append((position, location))

        reserved_by_item = dict(
            self.session.execute(
                select(
                    RequestLine.item_id,
                    func.sum(
                        RequestLine.requested_qty
                        - RequestLine.issued_qty
                        - RequestLine.cancelled_qty
                    ),
                )
                .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
                .where(
                    RequestLine.warehouse_id == self.user.warehouse_id,
                    RequestLine.item_id.in_(item_ids),
                    MaterialRequest.state.in_(OPEN_REQUEST_STATES),
                )
                .group_by(RequestLine.item_id)
            ).all()
        )
        allocated_by_item = dict(
            self.session.execute(
                select(
                    RequestLine.item_id,
                    func.sum(
                        Allocation.quantity - Allocation.issued_qty - Allocation.released_qty
                    ),
                )
                .join(RequestLine, RequestLine.id == Allocation.request_line_id)
                .where(
                    Allocation.warehouse_id == self.user.warehouse_id,
                    RequestLine.item_id.in_(item_ids),
                )
                .group_by(RequestLine.item_id)
            ).all()
        )

        response: list[InventoryItemResponse] = []
        for item, uom_code in item_rows:
            item_positions = positions_by_item[item.id]
            on_hand = sum((position.on_hand for position, _ in item_positions), Decimal("0"))
            quarantined = sum(
                (position.quarantined_qty for position, _ in item_positions), Decimal("0")
            )
            summary = StockSummary(
                on_hand=on_hand,
                quarantined=quarantined,
                reserved_demand=reserved_by_item.get(item.id, Decimal("0")),
                allocated=allocated_by_item.get(item.id, Decimal("0")),
            )
            response.append(
                InventoryItemResponse(
                    id=item.id,
                    sku=item.sku,
                    description=item.description,
                    inventory_path=item.inventory_path,
                    uom=uom_code,
                    on_hand=summary.usable_on_hand,
                    quarantined_qty=quarantined,
                    reserved_demand=summary.reserved_demand,
                    allocated_qty=summary.allocated,
                    free_to_promise=summary.free_to_promise,
                    shortage_qty=summary.shortage,
                    reorder_point=item.reorder_point,
                    locations=[
                        StockLocationResponse(
                            stock_position_id=position.id,
                            location_id=location.id,
                            location_code=location.code,
                            pick_sequence=location.pick_sequence,
                            on_hand=position.on_hand,
                            quarantined_qty=position.quarantined_qty,
                        )
                        for position, location in item_positions
                    ],
                )
            )
        return response

    def receive(
        self, *, stock_position_id: UUID, quantity: Decimal, reason: str
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        self._assert_spectrum_capability(item, "post_receipt")
        before = position.on_hand
        position.on_hand += quantity
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.RECEIPT,
            item=item,
            position=position,
            quantity=quantity,
            reason=reason,
            source_workflow="inventory_receipt",
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.received",
            entity_type="stock_position",
            entity_id=position.id,
            changes={"on_hand": {"before": str(before), "after": str(position.on_hand)}},
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def return_stock(
        self,
        *,
        stock_position_id: UUID,
        quantity: Decimal,
        condition: str,
        reason: str,
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        self._assert_spectrum_capability(item, "post_return")
        before_on_hand = position.on_hand
        before_quarantined = position.quarantined_qty
        position.on_hand += quantity
        if condition == "quarantined":
            position.quarantined_qty += quantity
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.RETURN,
            item=item,
            position=position,
            quantity=quantity,
            reason=f"Condition: {condition}. {reason}",
            source_workflow="jobsite_return",
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.returned",
            entity_type="stock_position",
            entity_id=position.id,
            changes={
                "on_hand": {"before": str(before_on_hand), "after": str(position.on_hand)},
                "quarantined_qty": {
                    "before": str(before_quarantined),
                    "after": str(position.quarantined_qty),
                },
                "condition": condition,
            },
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def quarantine(
        self, *, stock_position_id: UUID, quantity: Decimal, reason: str
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        self._assert_spectrum_capability(item, "post_adjustment")
        usable = position.on_hand - position.quarantined_qty
        if quantity > usable:
            raise ConflictError("Quarantine quantity exceeds usable stock")
        before = position.quarantined_qty
        position.quarantined_qty += quantity
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.QUARANTINE,
            item=item,
            position=position,
            quantity=quantity,
            reason=reason,
            source_workflow="inventory_quarantine",
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.quarantined",
            entity_type="stock_position",
            entity_id=position.id,
            changes={
                "quarantined_qty": {
                    "before": str(before),
                    "after": str(position.quarantined_qty),
                }
            },
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def release(
        self, *, stock_position_id: UUID, quantity: Decimal, reason: str
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        self._assert_spectrum_capability(item, "post_adjustment")
        if quantity > position.quarantined_qty:
            raise ConflictError("Release quantity exceeds quarantined stock")
        before = position.quarantined_qty
        position.quarantined_qty -= quantity
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.RELEASE,
            item=item,
            position=position,
            quantity=quantity,
            reason=reason,
            source_workflow="inventory_release",
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.released",
            entity_type="stock_position",
            entity_id=position.id,
            changes={
                "quarantined_qty": {
                    "before": str(before),
                    "after": str(position.quarantined_qty),
                }
            },
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def withdraw_general_use(
        self,
        *,
        stock_position_id: UUID,
        recipient_id: UUID,
        quantity: Decimal,
        note: str | None,
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        if item.inventory_path != InventoryPath.LOCAL_GENERAL_USE:
            raise ConflictError("Only local-general-use items can use quick withdrawal")
        recipient = self.session.scalar(
            select(EmployeeRecipient).where(
                EmployeeRecipient.id == recipient_id,
                EmployeeRecipient.warehouse_id == self.user.warehouse_id,
                EmployeeRecipient.is_active.is_(True),
            )
        )
        if recipient is None:
            raise NotFoundError("Recipient not found")
        delegated_roles = {Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER}
        if (
            not self.user.roles.intersection(delegated_roles)
            and recipient.linked_user_id != self.user.id
        ):
            raise PermissionDeniedError(
                "Employees can only withdraw general-use stock for themselves"
            )
        usable = position.on_hand - position.quarantined_qty
        if quantity > usable:
            raise ConflictError("Withdrawal quantity exceeds usable stock")

        before = position.on_hand
        position.on_hand -= quantity
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.GENERAL_USE_WITHDRAWAL,
            item=item,
            position=position,
            quantity=quantity,
            reason=note,
            source_workflow="general_use",
            recipient_id=recipient.id,
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.general_use_withdrawn",
            entity_type="stock_position",
            entity_id=position.id,
            changes={
                "on_hand": {"before": str(before), "after": str(position.on_hand)},
                "recipient_id": str(recipient.id),
            },
            reason=note,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def move(
        self,
        *,
        source_stock_position_id: UUID,
        destination_stock_position_id: UUID,
        quantity: Decimal,
        reason: str,
    ) -> InventoryMutationResponse:
        if source_stock_position_id == destination_stock_position_id:
            raise ConflictError("Source and destination must differ")
        position_ids = sorted(
            (source_stock_position_id, destination_stock_position_id), key=str
        )
        positions = list(
            self.session.scalars(
                select(StockPosition)
                .where(
                    StockPosition.id.in_(position_ids),
                    StockPosition.warehouse_id == self.user.warehouse_id,
                )
                .order_by(StockPosition.id)
                .with_for_update()
            ).all()
        )
        if len(positions) != 2:
            raise NotFoundError("Source or destination stock position not found")
        by_id = {position.id: position for position in positions}
        source = by_id[source_stock_position_id]
        destination = by_id[destination_stock_position_id]
        if source.item_id != destination.item_id:
            raise ConflictError("Inventory can only move between positions for the same item")
        if quantity > source.on_hand - source.quarantined_qty:
            raise ConflictError("Move quantity exceeds usable stock")

        item = self.session.get(Item, source.item_id)
        if item is None:
            raise NotFoundError("Item not found")
        source.on_hand -= quantity
        destination.on_hand += quantity
        source.version += 1
        destination.version += 1
        destination_location_id = destination.location_id
        event = self._inventory_event(
            InventoryEventType.MOVE,
            item=item,
            position=source,
            quantity=quantity,
            reason=reason,
            source_workflow="inventory_move",
            destination_location_id=destination_location_id,
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.moved",
            entity_type="inventory_event",
            entity_id=event.id,
            changes={
                "source_stock_position_id": str(source.id),
                "destination_stock_position_id": str(destination.id),
                "quantity": str(quantity),
            },
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, source)

    def adjust(
        self, *, stock_position_id: UUID, counted_on_hand: Decimal, reason: str
    ) -> InventoryMutationResponse:
        position, item = self._locked_position_with_item(stock_position_id)
        self._assert_spectrum_capability(item, "post_adjustment")
        if counted_on_hand < position.quarantined_qty:
            raise ConflictError("Count cannot be below quarantined quantity")
        before = position.on_hand
        position.on_hand = counted_on_hand
        position.version += 1
        event = self._inventory_event(
            InventoryEventType.COUNT_ADJUSTMENT,
            item=item,
            position=position,
            quantity=counted_on_hand - before,
            reason=reason,
            source_workflow="cycle_count",
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="inventory.count_adjusted",
            entity_type="stock_position",
            entity_id=position.id,
            changes={"on_hand": {"before": str(before), "after": str(counted_on_hand)}},
            reason=reason,
        )
        self.session.commit()
        return self._mutation_response(event, position)

    def list_events(self, limit: int = 100) -> list[InventoryEventResponse]:
        destination = aliased(Location)
        rows = self.session.execute(
            select(
                InventoryEvent,
                Item.sku,
                Location.code,
                destination.code,
                UnitOfMeasure.code,
                User.display_name,
            )
            .join(Item, Item.id == InventoryEvent.item_id)
            .join(UnitOfMeasure, UnitOfMeasure.id == InventoryEvent.uom_id)
            .join(User, User.id == InventoryEvent.actor_user_id)
            .outerjoin(Location, Location.id == InventoryEvent.location_id)
            .outerjoin(destination, destination.id == InventoryEvent.destination_location_id)
            .where(InventoryEvent.warehouse_id == self.user.warehouse_id)
            .order_by(InventoryEvent.created_at.desc())
            .limit(limit)
        ).all()
        return [
            InventoryEventResponse(
                id=event.id,
                event_type=event.event_type,
                item_id=event.item_id,
                sku=sku,
                location_code=location_code,
                destination_location_code=destination_code,
                quantity=event.quantity,
                uom=uom,
                reason=event.reason,
                actor_name=actor_name,
                created_at=event.created_at.isoformat(),
            )
            for event, sku, location_code, destination_code, uom, actor_name in rows
        ]

    def _locked_position_with_item(self, stock_position_id: UUID) -> tuple[StockPosition, Item]:
        row = self.session.execute(
            select(StockPosition, Item)
            .join(Item, Item.id == StockPosition.item_id)
            .where(
                StockPosition.id == stock_position_id,
                StockPosition.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise NotFoundError("Stock position not found")
        return row

    def _assert_spectrum_capability(self, item: Item, capability: str) -> None:
        if (
            item.inventory_path == InventoryPath.SPECTRUM_MANAGED
            and not self.spectrum_capabilities.get(capability, False)
        ):
            raise ConflictError(
                f"Spectrum-managed {capability.replace('_', ' ')} is not enabled"
            )

    def _inventory_event(
        self,
        event_type: InventoryEventType,
        *,
        item: Item,
        position: StockPosition,
        quantity: Decimal,
        reason: str | None,
        source_workflow: str,
        recipient_id: UUID | None = None,
        destination_location_id: UUID | None = None,
    ) -> InventoryEvent:
        event = InventoryEvent(
            warehouse_id=self.user.warehouse_id,
            event_type=event_type,
            actor_user_id=self.user.id,
            recipient_id=recipient_id,
            item_id=item.id,
            location_id=position.location_id,
            destination_location_id=destination_location_id,
            quantity=quantity,
            uom_id=item.uom_id,
            reason=reason,
            source_workflow=source_workflow,
        )
        self.session.add(event)
        self.session.flush()
        return event

    @staticmethod
    def _mutation_response(
        event: InventoryEvent, position: StockPosition
    ) -> InventoryMutationResponse:
        return InventoryMutationResponse(
            event_id=event.id,
            stock_position_id=position.id,
            event_type=event.event_type,
            on_hand=position.on_hand,
        )
