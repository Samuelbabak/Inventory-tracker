from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.domain.enums import OutboxStatus, RequestState
from app.domain.errors import ConflictError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.catalog.models import (
    ApprovedAlternate,
    Item,
    UnitConversion,
    UnitOfMeasure,
)
from app.modules.catalog.schemas import (
    ApprovedAlternateResponse,
    CatalogItemResponse,
    CatalogSnapshotResponse,
    CreateCatalogItemRequest,
    CreateUnitConversionRequest,
    CreateUnitOfMeasureRequest,
    UnitConversionResponse,
    UnitOfMeasureResponse,
    UpdateCatalogItemRequest,
)
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.models import InventoryEvent, StockPosition
from app.modules.requests.models import MaterialRequest, RequestLine
from app.modules.spectrum.models import OutboxEvent

OPEN_REQUEST_STATES = (
    RequestState.SUBMITTED,
    RequestState.CLAIMED,
    RequestState.IN_PROGRESS,
    RequestState.READY,
    RequestState.PARTIALLY_FULFILLED,
    RequestState.ON_HOLD,
)


class CatalogService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def snapshot(self) -> CatalogSnapshotResponse:
        item_rows = self.session.execute(
            select(Item, UnitOfMeasure.code)
            .join(UnitOfMeasure, UnitOfMeasure.id == Item.uom_id)
            .where(Item.warehouse_id == self.user.warehouse_id)
            .order_by(Item.sku)
        ).all()
        units = self.session.scalars(
            select(UnitOfMeasure).order_by(UnitOfMeasure.code)
        ).all()
        from_uom = aliased(UnitOfMeasure)
        to_uom = aliased(UnitOfMeasure)
        conversion_rows = self.session.execute(
            select(UnitConversion, from_uom.code, to_uom.code)
            .join(from_uom, from_uom.id == UnitConversion.from_uom_id)
            .join(to_uom, to_uom.id == UnitConversion.to_uom_id)
            .where(UnitConversion.warehouse_id == self.user.warehouse_id)
            .order_by(UnitConversion.created_at)
        ).all()
        requested_item = aliased(Item)
        alternate_item = aliased(Item)
        alternate_rows = self.session.execute(
            select(ApprovedAlternate, requested_item.sku, alternate_item.sku)
            .join(requested_item, requested_item.id == ApprovedAlternate.item_id)
            .join(alternate_item, alternate_item.id == ApprovedAlternate.alternate_item_id)
            .where(ApprovedAlternate.warehouse_id == self.user.warehouse_id)
            .order_by(requested_item.sku, alternate_item.sku)
        ).all()
        return CatalogSnapshotResponse(
            items=[self._item_response(item, uom) for item, uom in item_rows],
            units=[self._unit_response(unit) for unit in units],
            conversions=[
                self._conversion_response(conversion, source, destination)
                for conversion, source, destination in conversion_rows
            ],
            alternates=[
                self._alternate_response(alternate, item_sku, alternate_sku)
                for alternate, item_sku, alternate_sku in alternate_rows
            ],
        )

    def create_unit(self, payload: CreateUnitOfMeasureRequest) -> UnitOfMeasureResponse:
        code = payload.code.strip().upper()
        if self.session.scalar(select(UnitOfMeasure.id).where(UnitOfMeasure.code == code)):
            raise ConflictError("Unit code already exists")
        unit = UnitOfMeasure(
            code=code,
            name=payload.name.strip(),
            decimal_places=payload.decimal_places,
        )
        self.session.add(unit)
        self.session.flush()
        self._audit(
            action="catalog.uom_created",
            entity_type="unit_of_measure",
            entity_id=unit.id,
            changes={"code": unit.code, "decimal_places": unit.decimal_places},
        )
        self.session.commit()
        return self._unit_response(unit)

    def create_item(self, payload: CreateCatalogItemRequest) -> CatalogItemResponse:
        sku = payload.sku.strip().upper()
        if self.session.scalar(
            select(Item.id).where(
                Item.warehouse_id == self.user.warehouse_id,
                Item.sku == sku,
            )
        ):
            raise ConflictError("Item SKU already exists")
        unit = self.session.get(UnitOfMeasure, payload.uom_id)
        if unit is None:
            raise NotFoundError("Unit of measure not found")
        item = Item(
            warehouse_id=self.user.warehouse_id,
            sku=sku,
            description=payload.description.strip(),
            inventory_path=payload.inventory_path,
            spectrum_item_id=payload.spectrum_item_id,
            uom_id=unit.id,
            reorder_point=payload.reorder_point,
        )
        self.session.add(item)
        self.session.flush()
        self._audit(
            action="catalog.item_created",
            entity_type="item",
            entity_id=item.id,
            changes={"sku": item.sku, "inventory_path": item.inventory_path.value},
        )
        self.session.commit()
        return self._item_response(item, unit.code)

    def update_item(
        self, item_id: UUID, payload: UpdateCatalogItemRequest
    ) -> CatalogItemResponse:
        item = self._locked_item(item_id)
        if item.inventory_path != payload.inventory_path:
            self._assert_accounting_path_change_allowed(item)
        if item.is_active and not payload.is_active:
            self._assert_item_can_be_hidden(item)
        changes = {
            "description": [item.description, payload.description.strip()],
            "inventory_path": [item.inventory_path.value, payload.inventory_path.value],
            "spectrum_item_id": [item.spectrum_item_id, payload.spectrum_item_id],
            "reorder_point": [str(item.reorder_point), str(payload.reorder_point)],
            "is_active": [item.is_active, payload.is_active],
        }
        item.description = payload.description.strip()
        item.inventory_path = payload.inventory_path
        item.spectrum_item_id = payload.spectrum_item_id
        item.reorder_point = payload.reorder_point
        item.is_active = payload.is_active
        self._audit(
            action="catalog.item_updated",
            entity_type="item",
            entity_id=item.id,
            changes=changes,
            reason=payload.reason,
        )
        self.session.commit()
        unit_code = self.session.scalar(
            select(UnitOfMeasure.code).where(UnitOfMeasure.id == item.uom_id)
        )
        if unit_code is None:
            raise NotFoundError("Unit of measure not found")
        return self._item_response(item, unit_code)

    def create_conversion(
        self, payload: CreateUnitConversionRequest
    ) -> UnitConversionResponse:
        item = self._locked_item(payload.item_id)
        if payload.from_uom_id == payload.to_uom_id:
            raise ConflictError("Conversion units must differ")
        units = self.session.scalars(
            select(UnitOfMeasure).where(
                UnitOfMeasure.id.in_((payload.from_uom_id, payload.to_uom_id))
            )
        ).all()
        if len(units) != 2:
            raise NotFoundError("Conversion unit not found")
        by_id = {unit.id: unit for unit in units}
        conversion = self.session.scalar(
            select(UnitConversion).where(
                UnitConversion.item_id == item.id,
                UnitConversion.from_uom_id == payload.from_uom_id,
                UnitConversion.to_uom_id == payload.to_uom_id,
            )
        )
        if conversion is None:
            conversion = UnitConversion(
                warehouse_id=self.user.warehouse_id,
                item_id=item.id,
                from_uom_id=payload.from_uom_id,
                to_uom_id=payload.to_uom_id,
                factor=payload.factor,
            )
            self.session.add(conversion)
            self.session.flush()
        else:
            conversion.factor = payload.factor
        self._audit(
            action="catalog.conversion_saved",
            entity_type="unit_conversion",
            entity_id=conversion.id,
            changes={"item_id": str(item.id), "factor": str(payload.factor)},
            reason=payload.reason,
        )
        self.session.commit()
        return self._conversion_response(
            conversion,
            by_id[payload.from_uom_id].code,
            by_id[payload.to_uom_id].code,
        )

    def approve_alternate(
        self, item_id: UUID, alternate_item_id: UUID, reason: str
    ) -> ApprovedAlternateResponse:
        if item_id == alternate_item_id:
            raise ConflictError("An item cannot substitute for itself")
        items = self.session.scalars(
            select(Item)
            .where(
                Item.id.in_((item_id, alternate_item_id)),
                Item.warehouse_id == self.user.warehouse_id,
                Item.is_active.is_(True),
            )
            .with_for_update()
        ).all()
        if len(items) != 2:
            raise NotFoundError("Catalog item not found")
        by_id = {item.id: item for item in items}
        requested = by_id[item_id]
        alternate = by_id[alternate_item_id]
        if requested.inventory_path != alternate.inventory_path:
            raise ConflictError("Approved substitutes must use the same inventory path")
        if requested.uom_id != alternate.uom_id:
            raise ConflictError("Approved substitutes must use the same base UOM")
        if self.session.scalar(
            select(ApprovedAlternate.id).where(
                ApprovedAlternate.warehouse_id == self.user.warehouse_id,
                ApprovedAlternate.item_id == item_id,
                ApprovedAlternate.alternate_item_id == alternate_item_id,
            )
        ):
            raise ConflictError("Approved substitute already exists")
        approval = ApprovedAlternate(
            warehouse_id=self.user.warehouse_id,
            item_id=item_id,
            alternate_item_id=alternate_item_id,
        )
        self.session.add(approval)
        self.session.flush()
        self._audit(
            action="catalog.alternate_approved",
            entity_type="approved_alternate",
            entity_id=approval.id,
            changes={"item_id": str(item_id), "alternate_item_id": str(alternate_item_id)},
            reason=reason,
        )
        self.session.commit()
        return self._alternate_response(
            approval, requested.sku, alternate.sku
        )

    def revoke_alternate(
        self, alternate_id: UUID, reason: str
    ) -> ApprovedAlternateResponse:
        requested_item = aliased(Item)
        alternate_item = aliased(Item)
        row = self.session.execute(
            select(ApprovedAlternate, requested_item.sku, alternate_item.sku)
            .join(requested_item, requested_item.id == ApprovedAlternate.item_id)
            .join(alternate_item, alternate_item.id == ApprovedAlternate.alternate_item_id)
            .where(
                ApprovedAlternate.id == alternate_id,
                ApprovedAlternate.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise NotFoundError("Approved substitute not found")
        approval, item_sku, alternate_sku = row
        response = self._alternate_response(approval, item_sku, alternate_sku)
        self._audit(
            action="catalog.alternate_revoked",
            entity_type="approved_alternate",
            entity_id=approval.id,
            changes={
                "item_id": str(approval.item_id),
                "alternate_item_id": str(approval.alternate_item_id),
            },
            reason=reason,
        )
        self.session.delete(approval)
        self.session.commit()
        return response

    def _assert_accounting_path_change_allowed(self, item: Item) -> None:
        open_demand = self.session.scalar(
            select(RequestLine.id)
            .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
            .where(
                RequestLine.item_id == item.id,
                MaterialRequest.state.in_(OPEN_REQUEST_STATES),
            )
            .limit(1)
        )
        on_hand = self.session.scalar(
            select(func.coalesce(func.sum(StockPosition.on_hand), 0)).where(
                StockPosition.item_id == item.id
            )
        )
        unreconciled_issue = self.session.scalar(
            select(OutboxEvent.id)
            .join(InventoryEvent, InventoryEvent.id == OutboxEvent.aggregate_id)
            .where(
                InventoryEvent.item_id == item.id,
                OutboxEvent.status != OutboxStatus.SUCCEEDED,
            )
            .limit(1)
        )
        if open_demand or on_hand or unreconciled_issue:
            raise ConflictError(
                "Accounting path cannot change while demand, stock, or unreconciled issues exist"
            )

    def _assert_item_can_be_hidden(self, item: Item) -> None:
        on_hand = self.session.scalar(
            select(func.coalesce(func.sum(StockPosition.on_hand), 0)).where(
                StockPosition.item_id == item.id
            )
        )
        open_demand = self.session.scalar(
            select(RequestLine.id)
            .join(MaterialRequest, MaterialRequest.id == RequestLine.request_id)
            .where(
                RequestLine.item_id == item.id,
                MaterialRequest.state.in_(OPEN_REQUEST_STATES),
            )
            .limit(1)
        )
        if on_hand or open_demand:
            raise ConflictError("Items with stock or open demand cannot be deactivated")

    def _locked_item(self, item_id: UUID) -> Item:
        item = self.session.scalar(
            select(Item)
            .where(
                Item.id == item_id,
                Item.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if item is None:
            raise NotFoundError("Catalog item not found")
        return item

    def _audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID,
        changes: dict,
        reason: str | None = None,
    ) -> None:
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            reason=reason,
        )

    @staticmethod
    def _unit_response(unit: UnitOfMeasure) -> UnitOfMeasureResponse:
        return UnitOfMeasureResponse(
            id=unit.id,
            code=unit.code,
            name=unit.name,
            decimal_places=unit.decimal_places,
        )

    @staticmethod
    def _item_response(item: Item, uom: str) -> CatalogItemResponse:
        return CatalogItemResponse(
            id=item.id,
            sku=item.sku,
            description=item.description,
            inventory_path=item.inventory_path,
            spectrum_item_id=item.spectrum_item_id,
            uom_id=item.uom_id,
            uom=uom,
            reorder_point=item.reorder_point,
            is_active=item.is_active,
        )

    @staticmethod
    def _conversion_response(
        conversion: UnitConversion, source: str, destination: str
    ) -> UnitConversionResponse:
        return UnitConversionResponse(
            id=conversion.id,
            item_id=conversion.item_id,
            from_uom_id=conversion.from_uom_id,
            from_uom=source,
            to_uom_id=conversion.to_uom_id,
            to_uom=destination,
            factor=conversion.factor,
        )

    @staticmethod
    def _alternate_response(
        approval: ApprovedAlternate, item_sku: str, alternate_sku: str
    ) -> ApprovedAlternateResponse:
        return ApprovedAlternateResponse(
            id=approval.id,
            item_id=approval.item_id,
            item_sku=item_sku,
            alternate_item_id=approval.alternate_item_id,
            alternate_sku=alternate_sku,
        )