from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import InventoryPath, RequestPriority, RequestState


class RequestLineInput(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class CreateMaterialRequest(BaseModel):
    recipient_id: UUID
    priority: RequestPriority = RequestPriority.NORMAL
    urgent_reason: str | None = Field(default=None, max_length=500)
    job_number: str | None = Field(default=None, max_length=80)
    cost_code: str | None = Field(default=None, max_length=80)
    lines: list[RequestLineInput] = Field(min_length=1, max_length=100)
    submit: bool = True

    @model_validator(mode="after")
    def require_urgent_reason(self) -> "CreateMaterialRequest":
        if self.priority == RequestPriority.URGENT and not self.urgent_reason:
            raise ValueError("Urgent requests require a reason")
        return self


class AllocationResponse(BaseModel):
    id: UUID
    stock_position_id: UUID
    fulfillment_item_id: UUID
    fulfillment_sku: str
    fulfillment_description: str
    fulfillment_uom: str
    is_substitute: bool
    location_code: str
    quantity: Decimal
    picked_qty: Decimal
    issued_qty: Decimal
    released_qty: Decimal
    pick_confirmed: bool


class RequestLineResponse(BaseModel):
    id: UUID
    item_id: UUID
    sku: str
    description: str
    inventory_path: InventoryPath
    uom: str
    requested_qty: Decimal
    allocated_qty: Decimal
    picked_qty: Decimal
    issued_qty: Decimal
    cancelled_qty: Decimal
    backordered_qty: Decimal
    allocations: list[AllocationResponse]


class MaterialRequestResponse(BaseModel):
    id: UUID
    request_number: str
    state: RequestState
    priority: RequestPriority
    urgent_reason: str | None
    job_number: str | None
    cost_code: str | None
    creator_name: str
    recipient_name: str
    claimed_by_user_id: UUID | None
    claimed_by_name: str | None
    version: int
    created_at: str
    updated_at: str
    lines: list[RequestLineResponse]


class RecordPickRequest(BaseModel):
    allocation_id: UUID
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    scanned_location_code: str = Field(min_length=1, max_length=80)
    scanned_sku: str = Field(min_length=1, max_length=80)
    shortage_reason: str | None = Field(default=None, max_length=500)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReallocateStockRequest(BaseModel):
    source_allocation_id: UUID
    target_request_line_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class ReallocationResponse(BaseModel):
    source_request: MaterialRequestResponse
    target_request: MaterialRequestResponse


class SubstituteAllocationRequest(BaseModel):
    allocation_id: UUID
    alternate_stock_position_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class SubstituteCandidateResponse(BaseModel):
    stock_position_id: UUID
    item_id: UUID
    sku: str
    description: str
    location_code: str
    available_qty: Decimal
    uom: str
