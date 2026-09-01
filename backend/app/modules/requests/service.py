from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.domain.enums import (
    InventoryEventType,
    InventoryPath,
    OutboxStatus,
    RequestPriority,
    RequestState,
    Role,
)
from app.domain.errors import (
    ConflictError,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
)
from app.modules.audit.service import record_audit
from app.modules.catalog.models import ApprovedAlternate, Item, UnitOfMeasure
from app.modules.fulfillment.models import FulfillmentBatch
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.models import InventoryEvent, StockPosition
from app.modules.locations.models import Location
from app.modules.notifications.service import notify_user
from app.modules.recipients.models import EmployeeRecipient
from app.modules.requests.models import Allocation, MaterialRequest, RequestLine
from app.modules.requests.schemas import (
    AllocationResponse,
    CreateMaterialRequest,
    MaterialRequestResponse,
    ReallocationResponse,
    RequestLineResponse,
    SubstituteCandidateResponse,
)
from app.modules.spectrum.models import OutboxEvent
from app.platform.database.base import utc_now

ZERO = Decimal("0")
WAREHOUSE_ROLES = frozenset(
    {Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR}
)
CLAIMABLE_STATES = (RequestState.SUBMITTED, RequestState.PARTIALLY_FULFILLED)
REALLOCATABLE_STATES = (
    RequestState.SUBMITTED,
    RequestState.PARTIALLY_FULFILLED,
    RequestState.ON_HOLD,
)


class RequestService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def create(self, payload: CreateMaterialRequest) -> MaterialRequestResponse:
        recipient = self.session.scalar(
            select(EmployeeRecipient).where(
                EmployeeRecipient.id == payload.recipient_id,
                EmployeeRecipient.warehouse_id == self.user.warehouse_id,
                EmployeeRecipient.is_active.is_(True),
            )
        )
        if recipient is None:
            raise NotFoundError("Recipient not found")

        requested_item_ids = [line.item_id for line in payload.lines]
        items = list(
            self.session.scalars(
                select(Item).where(
                    Item.id.in_(requested_item_ids),
                    Item.warehouse_id == self.user.warehouse_id,
                    Item.is_active.is_(True),
                )
            ).all()
        )
        items_by_id = {item.id: item for item in items}
        if len(items_by_id) != len(set(requested_item_ids)):
            raise NotFoundError("One or more request items were not found")
        if any(
            item.inventory_path == InventoryPath.SPECTRUM_MANAGED for item in items
        ) and not payload.job_number:
            raise ConflictError("Spectrum-managed request lines require a job number")

        material_request = MaterialRequest(
            warehouse_id=self.user.warehouse_id,
            request_number=self._new_request_number(),
            creator_user_id=self.user.id,
            recipient_id=recipient.id,
            priority=payload.priority,
            urgent_reason=payload.urgent_reason,
            job_number=payload.job_number,
            cost_code=payload.cost_code,
        )
        self.session.add(material_request)
        self.session.flush()
        for requested_line in payload.lines:
            self.session.add(
                RequestLine(
                    warehouse_id=self.user.warehouse_id,
                    request_id=material_request.id,
                    item_id=requested_line.item_id,
                    requested_qty=requested_line.quantity,
                )
            )
        self.session.flush()
        if payload.submit:
            self._submit_locked(material_request)
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="request.created",
            entity_type="material_request",
            entity_id=material_request.id,
            changes={"state": material_request.state.value, "line_count": len(payload.lines)},
            reason=payload.urgent_reason,
        )
        self.session.commit()
        return self.get(material_request.id)

    def submit(self, request_id: UUID) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        if material_request.creator_user_id != self.user.id and not (
            self.user.roles & WAREHOUSE_ROLES
        ):
            raise PermissionDeniedError(
                "Only the creator or warehouse staff can submit this request"
            )
        self._submit_locked(material_request)
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="request.submitted",
            entity_type="material_request",
            entity_id=material_request.id,
            changes={"state": RequestState.SUBMITTED.value},
        )
        self.session.commit()
        return self.get(material_request.id)

    def list(self, *, mine_only: bool = False) -> list[MaterialRequestResponse]:
        query = select(MaterialRequest.id).where(
            MaterialRequest.warehouse_id == self.user.warehouse_id
        )
        if mine_only or not (self.user.roles & WAREHOUSE_ROLES):
            query = query.where(MaterialRequest.creator_user_id == self.user.id)
        query = query.order_by(
            case((MaterialRequest.priority == RequestPriority.URGENT, 0), else_=1),
            MaterialRequest.created_at.desc(),
        )
        return [self.get(request_id) for request_id in self.session.scalars(query).all()]

    def get(self, request_id: UUID) -> MaterialRequestResponse:
        creator = aliased(User)
        claimer = aliased(User)
        row = self.session.execute(
            select(
                MaterialRequest,
                creator.display_name,
                EmployeeRecipient.display_name,
                claimer.display_name,
            )
            .join(creator, creator.id == MaterialRequest.creator_user_id)
            .join(EmployeeRecipient, EmployeeRecipient.id == MaterialRequest.recipient_id)
            .outerjoin(claimer, claimer.id == MaterialRequest.claimed_by_user_id)
            .where(
                MaterialRequest.id == request_id,
                MaterialRequest.warehouse_id == self.user.warehouse_id,
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Request not found")
        material_request, creator_name, recipient_name, claimer_name = row
        if material_request.creator_user_id != self.user.id and not (
            self.user.roles & WAREHOUSE_ROLES
        ):
            raise PermissionDeniedError("Request is not visible to this user")

        line_rows = self.session.execute(
            select(RequestLine, Item, UnitOfMeasure.code)
            .join(Item, Item.id == RequestLine.item_id)
            .join(UnitOfMeasure, UnitOfMeasure.id == Item.uom_id)
            .where(RequestLine.request_id == request_id)
            .order_by(Item.description)
        ).all()
        line_ids = [line.id for line, _, _ in line_rows]
        requested_item_by_line = {line.id: item.id for line, item, _ in line_rows}
        allocations_by_line: dict[UUID, list[AllocationResponse]] = defaultdict(list)
        if line_ids:
            fulfillment_item = aliased(Item)
            fulfillment_uom = aliased(UnitOfMeasure)
            allocation_rows = self.session.execute(
                select(
                    Allocation,
                    StockPosition,
                    Location.code,
                    fulfillment_item,
                    fulfillment_uom.code,
                )
                .join(StockPosition, StockPosition.id == Allocation.stock_position_id)
                .join(Location, Location.id == StockPosition.location_id)
                .join(fulfillment_item, fulfillment_item.id == StockPosition.item_id)
                .join(fulfillment_uom, fulfillment_uom.id == fulfillment_item.uom_id)
                .where(Allocation.request_line_id.in_(line_ids))
                .order_by(Location.pick_sequence)
            ).all()
            for (
                allocation,
                position,
                location_code,
                fulfilled_item,
                fulfilled_uom,
            ) in allocation_rows:
                allocations_by_line[allocation.request_line_id].append(
                    AllocationResponse(
                        id=allocation.id,
                        stock_position_id=position.id,
                        fulfillment_item_id=fulfilled_item.id,
                        fulfillment_sku=fulfilled_item.sku,
                        fulfillment_description=fulfilled_item.description,
                        fulfillment_uom=fulfilled_uom,
                        is_substitute=(
                            fulfilled_item.id
                            != requested_item_by_line[allocation.request_line_id]
                        ),
                        location_code=location_code,
                        quantity=allocation.quantity,
                        picked_qty=allocation.picked_qty,
                        issued_qty=allocation.issued_qty,
                        released_qty=allocation.released_qty,
                        pick_confirmed=allocation.pick_confirmed,
                    )
                )

        return MaterialRequestResponse(
            id=material_request.id,
            request_number=material_request.request_number,
            state=material_request.state,
            priority=material_request.priority,
            urgent_reason=material_request.urgent_reason,
            job_number=material_request.job_number,
            cost_code=material_request.cost_code,
            creator_name=creator_name,
            recipient_name=recipient_name,
            claimed_by_user_id=material_request.claimed_by_user_id,
            claimed_by_name=claimer_name,
            version=material_request.version,
            created_at=material_request.created_at.isoformat(),
            updated_at=material_request.updated_at.isoformat(),
            lines=[
                RequestLineResponse(
                    id=line.id,
                    item_id=item.id,
                    sku=item.sku,
                    description=item.description,
                    inventory_path=item.inventory_path,
                    uom=uom_code,
                    requested_qty=line.requested_qty,
                    allocated_qty=line.allocated_qty,
                    picked_qty=line.picked_qty,
                    issued_qty=line.issued_qty,
                    cancelled_qty=line.cancelled_qty,
                    backordered_qty=line.backordered_qty,
                    allocations=allocations_by_line[line.id],
                )
                for line, item, uom_code in line_rows
            ],
        )

    def claim(self, request_id: UUID) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        self._claim_locked(material_request)
        self.session.commit()
        return self.get(material_request.id)

    def claim_next(self) -> MaterialRequestResponse | None:
        material_request = self.session.scalar(
            select(MaterialRequest)
            .where(
                MaterialRequest.warehouse_id == self.user.warehouse_id,
                MaterialRequest.state.in_(CLAIMABLE_STATES),
                MaterialRequest.claimed_by_user_id.is_(None),
            )
            .order_by(
                case((MaterialRequest.priority == RequestPriority.URGENT, 0), else_=1),
                MaterialRequest.created_at,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if material_request is None:
            return None
        self._claim_locked(material_request)
        self.session.commit()
        return self.get(material_request.id)

    def reallocate(
        self,
        *,
        source_allocation_id: UUID,
        target_request_line_id: UUID,
        quantity: Decimal,
        reason: str,
    ) -> ReallocationResponse:
        if Role.INVENTORY_MANAGER not in self.user.roles:
            raise PermissionDeniedError("Only inventory managers can reallocate stock")
        source_row = self.session.execute(
            select(Allocation, RequestLine, MaterialRequest)
            .join(RequestLine, RequestLine.id == Allocation.request_line_id)
            .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
            .where(
                Allocation.id == source_allocation_id,
                Allocation.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        ).one_or_none()
        target_row = self.session.execute(
            select(RequestLine, MaterialRequest)
            .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
            .where(
                RequestLine.id == target_request_line_id,
                RequestLine.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        ).one_or_none()
        if source_row is None or target_row is None:
            raise NotFoundError("Source allocation or target request line not found")
        source_allocation, source_line, source_request = source_row
        target_line, target_request = target_row
        if source_request.id == target_request.id:
            raise ConflictError("Stock must be reallocated between different requests")
        if source_request.state not in REALLOCATABLE_STATES:
            raise InvalidStateError("Source request is not available for reallocation")
        if target_request.state not in REALLOCATABLE_STATES:
            raise InvalidStateError("Target request is not available for reallocation")
        if source_line.item_id != target_line.item_id:
            raise ConflictError("Reallocation requires the same requested item")
        transferable = (
            source_allocation.quantity
            - source_allocation.picked_qty
            - source_allocation.released_qty
        )
        if quantity > transferable:
            raise ConflictError("Reallocation quantity exceeds unpicked allocation")
        if quantity > target_line.backordered_qty:
            raise ConflictError("Reallocation quantity exceeds target backorder")

        source_allocation.released_qty += quantity
        if (
            source_allocation.issued_qty + source_allocation.released_qty
            == source_allocation.quantity
        ):
            source_allocation.pick_confirmed = True
        target_allocation = Allocation(
            warehouse_id=self.user.warehouse_id,
            request_line_id=target_line.id,
            stock_position_id=source_allocation.stock_position_id,
            quantity=quantity,
        )
        self.session.add(target_allocation)
        self.session.flush()
        self._refresh_line_totals(source_line)
        self._refresh_line_totals(target_line)
        source_request.version += 1
        target_request.version += 1

        item = self.session.get(Item, source_line.item_id)
        if item is None:
            raise NotFoundError("Item not found")
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=source_request.creator_user_id,
            title=f"{source_request.request_number} allocation changed",
            message=(
                f"{quantity} {item.sku} was reallocated to "
                f"{target_request.request_number}. Reason: {reason}"
            ),
            entity_type="material_request",
            entity_id=source_request.id,
        )
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=target_request.creator_user_id,
            title=f"{target_request.request_number} received stock",
            message=f"{quantity} {item.sku} was allocated. Reason: {reason}",
            entity_type="material_request",
            entity_id=target_request.id,
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="allocation.reallocated",
            entity_type="allocation",
            entity_id=source_allocation.id,
            changes={
                "target_allocation_id": str(target_allocation.id),
                "source_request_id": str(source_request.id),
                "target_request_id": str(target_request.id),
                "quantity": str(quantity),
            },
            reason=reason,
        )
        self.session.commit()
        return ReallocationResponse(
            source_request=self.get(source_request.id),
            target_request=self.get(target_request.id),
        )

    def substitute(
        self,
        request_id: UUID,
        *,
        allocation_id: UUID,
        alternate_stock_position_id: UUID,
        quantity: Decimal,
        reason: str,
    ) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        self._assert_claimed_by_user(material_request)
        source_row = self.session.execute(
            select(Allocation, RequestLine, StockPosition)
            .join(RequestLine, RequestLine.id == Allocation.request_line_id)
            .join(StockPosition, StockPosition.id == Allocation.stock_position_id)
            .where(
                Allocation.id == allocation_id,
                RequestLine.request_id == material_request.id,
            )
            .with_for_update()
        ).one_or_none()
        alternate_row = self.session.execute(
            select(StockPosition, Item)
            .join(Item, Item.id == StockPosition.item_id)
            .where(
                StockPosition.id == alternate_stock_position_id,
                StockPosition.warehouse_id == self.user.warehouse_id,
                Item.is_active.is_(True),
            )
            .with_for_update()
        ).one_or_none()
        if source_row is None or alternate_row is None:
            raise NotFoundError("Allocation or alternate stock position not found")
        source_allocation, line, source_position = source_row
        alternate_position, alternate_item = alternate_row
        if source_position.id == alternate_position.id:
            raise ConflictError("Alternate stock position must differ from the allocation")
        approved = self.session.scalar(
            select(ApprovedAlternate.id).where(
                ApprovedAlternate.warehouse_id == self.user.warehouse_id,
                ApprovedAlternate.item_id == line.item_id,
                ApprovedAlternate.alternate_item_id == alternate_item.id,
            )
        )
        if approved is None:
            raise ConflictError("The selected item is not an approved substitute")
        requested_item = self.session.get(Item, line.item_id)
        if requested_item is None:
            raise NotFoundError("Requested item not found")
        if alternate_item.inventory_path != requested_item.inventory_path:
            raise ConflictError("Substitutes must use the same inventory path")
        transferable = (
            source_allocation.quantity
            - source_allocation.picked_qty
            - source_allocation.released_qty
        )
        if quantity > transferable:
            raise ConflictError("Substitution quantity exceeds unpicked allocation")
        already_allocated = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        Allocation.quantity
                        - Allocation.issued_qty
                        - Allocation.released_qty
                    ),
                    ZERO,
                )
            ).where(Allocation.stock_position_id == alternate_position.id)
        )
        available = (
            alternate_position.on_hand
            - alternate_position.quarantined_qty
            - already_allocated
        )
        if quantity > available:
            raise ConflictError("Substitute quantity exceeds available stock")

        source_allocation.released_qty += quantity
        if (
            source_allocation.issued_qty + source_allocation.released_qty
            == source_allocation.quantity
        ):
            source_allocation.pick_confirmed = True
        replacement = Allocation(
            warehouse_id=self.user.warehouse_id,
            request_line_id=line.id,
            stock_position_id=alternate_position.id,
            quantity=quantity,
        )
        self.session.add(replacement)
        self.session.flush()
        self._refresh_line_totals(line)
        material_request.version += 1
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="fulfillment.substituted",
            entity_type="allocation",
            entity_id=replacement.id,
            changes={
                "requested_item_id": str(requested_item.id),
                "alternate_item_id": str(alternate_item.id),
                "source_allocation_id": str(source_allocation.id),
                "quantity": str(quantity),
            },
            reason=reason,
        )
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=material_request.creator_user_id,
            title=f"{material_request.request_number} substitution",
            message=(
                f"{quantity} {requested_item.sku} will be fulfilled with "
                f"{alternate_item.sku}. Reason: {reason}"
            ),
            entity_type="material_request",
            entity_id=material_request.id,
        )
        self.session.commit()
        return self.get(material_request.id)

    def list_substitute_candidates(
        self, request_id: UUID, allocation_id: UUID
    ) -> list[SubstituteCandidateResponse]:
        requested_item_id = self.session.scalar(
            select(RequestLine.item_id)
            .join(Allocation, Allocation.request_line_id == RequestLine.id)
            .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
            .where(
                MaterialRequest.id == request_id,
                MaterialRequest.warehouse_id == self.user.warehouse_id,
                MaterialRequest.claimed_by_user_id == self.user.id,
                Allocation.id == allocation_id,
            )
        )
        if requested_item_id is None:
            raise NotFoundError("Claimed allocation not found")

        committed = (
            select(
                Allocation.stock_position_id.label("stock_position_id"),
                func.sum(
                    Allocation.quantity
                    - Allocation.issued_qty
                    - Allocation.released_qty
                ).label("quantity"),
            )
            .group_by(Allocation.stock_position_id)
            .subquery()
        )
        available = (
            StockPosition.on_hand
            - StockPosition.quarantined_qty
            - func.coalesce(committed.c.quantity, ZERO)
        )
        rows = self.session.execute(
            select(
                StockPosition.id,
                Item.id,
                Item.sku,
                Item.description,
                Location.code,
                available,
                UnitOfMeasure.code,
            )
            .join(Item, Item.id == StockPosition.item_id)
            .join(Location, Location.id == StockPosition.location_id)
            .join(UnitOfMeasure, UnitOfMeasure.id == Item.uom_id)
            .join(
                ApprovedAlternate,
                ApprovedAlternate.alternate_item_id == Item.id,
            )
            .outerjoin(
                committed,
                committed.c.stock_position_id == StockPosition.id,
            )
            .where(
                StockPosition.warehouse_id == self.user.warehouse_id,
                ApprovedAlternate.item_id == requested_item_id,
                Item.is_active.is_(True),
                available > ZERO,
            )
            .order_by(Item.sku, Location.pick_sequence)
        ).all()
        return [
            SubstituteCandidateResponse(
                stock_position_id=stock_position_id,
                item_id=item_id,
                sku=sku,
                description=description,
                location_code=location_code,
                available_qty=available_qty,
                uom=uom,
            )
            for (
                stock_position_id,
                item_id,
                sku,
                description,
                location_code,
                available_qty,
                uom,
            ) in rows
        ]

    def record_pick(
        self,
        request_id: UUID,
        *,
        allocation_id: UUID,
        quantity: Decimal,
        scanned_location_code: str,
        scanned_sku: str,
        shortage_reason: str | None,
        commit: bool = True,
    ) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        self._assert_claimed_by_user(material_request)
        row = self.session.execute(
            select(Allocation, RequestLine, StockPosition, Location, Item)
            .join(RequestLine, RequestLine.id == Allocation.request_line_id)
            .join(StockPosition, StockPosition.id == Allocation.stock_position_id)
            .join(Location, Location.id == StockPosition.location_id)
            .join(Item, Item.id == StockPosition.item_id)
            .where(
                Allocation.id == allocation_id,
                RequestLine.request_id == material_request.id,
            )
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise NotFoundError("Allocation not found")
        allocation, line, _, location, item = row
        if location.code.casefold() != scanned_location_code.casefold():
            raise ConflictError("Scanned location does not match the allocation")
        if item.sku.casefold() != scanned_sku.casefold():
            raise ConflictError("Scanned item does not match the request line")

        available_allocation = allocation.quantity - allocation.released_qty
        if quantity < allocation.issued_qty or quantity > available_allocation:
            raise ConflictError("Picked quantity is outside the allocated range")
        shortage = available_allocation - quantity
        if shortage > ZERO and not shortage_reason:
            raise ConflictError("A reason is required when picked quantity is short")
        allocation.picked_qty = quantity
        allocation.released_qty += shortage
        allocation.pick_confirmed = True
        self._refresh_line_totals(line)

        confirmations = self.session.execute(
            select(Allocation.pick_confirmed).where(
                Allocation.request_line_id.in_(
                    select(RequestLine.id).where(
                        RequestLine.request_id == material_request.id
                    )
                )
            )
        ).scalars()
        material_request.state = (
            RequestState.READY if all(confirmations) else RequestState.IN_PROGRESS
        )
        material_request.version += 1
        batch = self.session.scalar(
            select(FulfillmentBatch).where(
                FulfillmentBatch.request_id == material_request.id,
                FulfillmentBatch.status == "picking",
            )
        )
        if batch is None:
            self.session.add(
                FulfillmentBatch(
                    warehouse_id=self.user.warehouse_id,
                    request_id=material_request.id,
                    worker_user_id=self.user.id,
                )
            )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="fulfillment.pick_confirmed",
            entity_type="allocation",
            entity_id=allocation.id,
            changes={"picked_qty": str(quantity), "shortage_qty": str(shortage)},
            reason=shortage_reason,
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return self.get(material_request.id)

    def handoff(self, request_id: UUID, *, commit: bool = True) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        self._assert_claimed_by_user(material_request)
        if material_request.state != RequestState.READY:
            raise InvalidStateError("Every allocation must be pick-confirmed before handoff")

        rows = self.session.execute(
            select(Allocation, RequestLine, StockPosition, Item)
            .join(RequestLine, RequestLine.id == Allocation.request_line_id)
            .join(StockPosition, StockPosition.id == Allocation.stock_position_id)
            .join(Item, Item.id == StockPosition.item_id)
            .where(RequestLine.request_id == material_request.id)
            .order_by(StockPosition.id)
            .with_for_update()
        ).all()
        affected_lines: dict[UUID, RequestLine] = {}
        issued_total = ZERO
        for allocation, line, position, item in rows:
            issue_quantity = allocation.picked_qty - allocation.issued_qty
            if issue_quantity <= ZERO:
                affected_lines[line.id] = line
                continue
            if issue_quantity > position.on_hand - position.quarantined_qty:
                raise ConflictError(f"Usable stock changed for {item.sku}; review is required")
            position.on_hand -= issue_quantity
            position.version += 1
            allocation.issued_qty += issue_quantity
            event = InventoryEvent(
                warehouse_id=self.user.warehouse_id,
                event_type=InventoryEventType.MATERIAL_ISSUE,
                actor_user_id=self.user.id,
                recipient_id=material_request.recipient_id,
                item_id=item.id,
                location_id=position.location_id,
                quantity=issue_quantity,
                uom_id=item.uom_id,
                source_workflow="request_handoff",
                reference_id=material_request.id,
            )
            self.session.add(event)
            self.session.flush()
            if item.inventory_path == InventoryPath.SPECTRUM_MANAGED:
                self.session.add(
                    OutboxEvent(
                        warehouse_id=self.user.warehouse_id,
                        event_type="material_issue",
                        aggregate_id=event.id,
                        payload={
                            "business_reference": str(event.id),
                            "request_number": material_request.request_number,
                            "spectrum_item_id": item.spectrum_item_id,
                            "sku": item.sku,
                            "quantity": str(issue_quantity),
                            "job_number": material_request.job_number,
                            "cost_code": material_request.cost_code,
                        },
                        status=OutboxStatus.PENDING,
                        available_at=utc_now(),
                    )
                )
            affected_lines[line.id] = line
            issued_total += issue_quantity

        for line in affected_lines.values():
            self._refresh_line_totals(line)
        all_lines = list(
            self.session.scalars(
                select(RequestLine).where(RequestLine.request_id == material_request.id)
            ).all()
        )
        fully_closed = all(
            line.issued_qty + line.cancelled_qty >= line.requested_qty
            for line in all_lines
        )
        material_request.state = (
            RequestState.COMPLETED if fully_closed else RequestState.PARTIALLY_FULFILLED
        )
        material_request.claimed_by_user_id = None
        material_request.version += 1
        batch = self.session.scalar(
            select(FulfillmentBatch).where(
                FulfillmentBatch.request_id == material_request.id,
                FulfillmentBatch.status == "picking",
            )
        )
        if batch:
            batch.status = "handed_off"
            batch.handed_off_at = utc_now()
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=material_request.creator_user_id,
            title=f"{material_request.request_number} handed off",
            message=f"{issued_total} units were issued. Status: {material_request.state.value}.",
            entity_type="material_request",
            entity_id=material_request.id,
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="fulfillment.handed_off",
            entity_type="material_request",
            entity_id=material_request.id,
            changes={"issued_qty": str(issued_total), "state": material_request.state.value},
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return self.get(material_request.id)

    def cancel(self, request_id: UUID, *, reason: str) -> MaterialRequestResponse:
        material_request = self._locked_request(request_id)
        if material_request.state in (RequestState.COMPLETED, RequestState.CANCELLED):
            raise InvalidStateError("Completed or cancelled requests cannot be cancelled")
        lines = list(
            self.session.scalars(
                select(RequestLine)
                .where(RequestLine.request_id == material_request.id)
                .with_for_update()
            ).all()
        )
        line_ids = [line.id for line in lines]
        allocations = list(
            self.session.scalars(
                select(Allocation)
                .where(Allocation.request_line_id.in_(line_ids))
                .with_for_update()
            ).all()
        )
        for allocation in allocations:
            allocation.released_qty = allocation.quantity - allocation.issued_qty
        for line in lines:
            line.cancelled_qty = line.requested_qty - line.issued_qty
            self._refresh_line_totals(line)
        material_request.state = RequestState.CANCELLED
        material_request.claimed_by_user_id = None
        material_request.version += 1
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="request.cancelled",
            entity_type="material_request",
            entity_id=material_request.id,
            changes={"state": RequestState.CANCELLED.value},
            reason=reason,
        )
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=material_request.creator_user_id,
            title=f"{material_request.request_number} cancelled",
            message=reason,
            entity_type="material_request",
            entity_id=material_request.id,
        )
        self.session.commit()
        return self.get(material_request.id)

    def _submit_locked(self, material_request: MaterialRequest) -> None:
        if material_request.state != RequestState.DRAFT:
            raise InvalidStateError("Only draft requests can be submitted")
        lines = list(
            self.session.scalars(
                select(RequestLine)
                .where(RequestLine.request_id == material_request.id)
                .order_by(RequestLine.created_at)
                .with_for_update()
            ).all()
        )
        for line in lines:
            remaining = line.requested_qty
            position_rows = self.session.execute(
                select(StockPosition, Location.pick_sequence)
                .join(Location, Location.id == StockPosition.location_id)
                .where(
                    StockPosition.warehouse_id == self.user.warehouse_id,
                    StockPosition.item_id == line.item_id,
                )
                .order_by(Location.pick_sequence, StockPosition.id)
                .with_for_update()
            ).all()
            for position, _ in position_rows:
                already_allocated = self.session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                Allocation.quantity
                                - Allocation.issued_qty
                                - Allocation.released_qty
                            ),
                            ZERO,
                        )
                    ).where(Allocation.stock_position_id == position.id)
                )
                available = position.on_hand - position.quarantined_qty - already_allocated
                allocated = min(max(available, ZERO), remaining)
                if allocated <= ZERO:
                    continue
                self.session.add(
                    Allocation(
                        warehouse_id=self.user.warehouse_id,
                        request_line_id=line.id,
                        stock_position_id=position.id,
                        quantity=allocated,
                    )
                )
                self.session.flush()
                line.allocated_qty += allocated
                remaining -= allocated
                if remaining == ZERO:
                    break
            line.backordered_qty = remaining
        material_request.state = RequestState.SUBMITTED
        material_request.version += 1

    def _claim_locked(self, material_request: MaterialRequest) -> None:
        if material_request.state not in CLAIMABLE_STATES:
            raise InvalidStateError("Request is not available to claim")
        if material_request.claimed_by_user_id not in (None, self.user.id):
            raise ConflictError("Request is already claimed")
        material_request.claimed_by_user_id = self.user.id
        material_request.state = RequestState.CLAIMED
        material_request.version += 1
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="fulfillment.claimed",
            entity_type="material_request",
            entity_id=material_request.id,
            changes={"state": RequestState.CLAIMED.value},
        )

    def _locked_request(self, request_id: UUID) -> MaterialRequest:
        material_request = self.session.scalar(
            select(MaterialRequest)
            .where(
                MaterialRequest.id == request_id,
                MaterialRequest.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if material_request is None:
            raise NotFoundError("Request not found")
        return material_request

    def _assert_claimed_by_user(self, material_request: MaterialRequest) -> None:
        if material_request.claimed_by_user_id != self.user.id:
            raise PermissionDeniedError("Request must be claimed by the current worker")

    def _refresh_line_totals(self, line: RequestLine) -> None:
        allocations = list(
            self.session.scalars(
                select(Allocation).where(Allocation.request_line_id == line.id)
            ).all()
        )
        line.picked_qty = sum((item.picked_qty for item in allocations), ZERO)
        line.issued_qty = sum((item.issued_qty for item in allocations), ZERO)
        line.allocated_qty = sum(
            (item.quantity - item.released_qty for item in allocations), ZERO
        )
        open_allocated = sum(
            (item.quantity - item.issued_qty - item.released_qty for item in allocations), ZERO
        )
        line.backordered_qty = max(
            line.requested_qty - line.issued_qty - line.cancelled_qty - open_allocated,
            ZERO,
        )
        line.version += 1

    @staticmethod
    def _new_request_number() -> str:
        date_part = datetime.now(UTC).strftime("%Y%m%d")
        return f"MR-{date_part}-{secrets.token_hex(3).upper()}"
