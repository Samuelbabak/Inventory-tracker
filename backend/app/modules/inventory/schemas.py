from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import InventoryEventType, InventoryPath


class StockLocationResponse(BaseModel):
    stock_position_id: UUID
    location_id: UUID
    location_code: str
    pick_sequence: int
    on_hand: Decimal
    quarantined_qty: Decimal


class InventoryItemResponse(BaseModel):
    id: UUID
    sku: str
    description: str
    inventory_path: InventoryPath
    uom: str
    on_hand: Decimal
    quarantined_qty: Decimal
    reserved_demand: Decimal
    allocated_qty: Decimal
    free_to_promise: Decimal
    shortage_qty: Decimal
    reorder_point: Decimal
    locations: list[StockLocationResponse]


class ReceiveInventoryRequest(BaseModel):
    stock_position_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class GeneralUseWithdrawalRequest(BaseModel):
    stock_position_id: UUID
    recipient_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    note: str | None = Field(default=None, max_length=500)


class MoveInventoryRequest(BaseModel):
    source_stock_position_id: UUID
    destination_stock_position_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class AdjustInventoryRequest(BaseModel):
    stock_position_id: UUID
    counted_on_hand: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class ReturnInventoryRequest(BaseModel):
    stock_position_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    condition: Literal["usable", "quarantined"]
    reason: str = Field(min_length=3, max_length=500)


class InventoryAvailabilityRequest(BaseModel):
    stock_position_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class InventoryMutationResponse(BaseModel):
    event_id: UUID
    stock_position_id: UUID
    event_type: InventoryEventType
    on_hand: Decimal


class InventoryEventResponse(BaseModel):
    id: UUID
    event_type: InventoryEventType
    item_id: UUID
    sku: str
    location_code: str | None
    destination_location_code: str | None
    quantity: Decimal
    uom: str
    reason: str | None
    actor_name: str
    created_at: str
