from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import InventoryPath


class UnitOfMeasureResponse(BaseModel):
    id: UUID
    code: str
    name: str
    decimal_places: int


class CatalogItemResponse(BaseModel):
    id: UUID
    sku: str
    description: str
    inventory_path: InventoryPath
    spectrum_item_id: str | None
    uom_id: UUID
    uom: str
    reorder_point: Decimal
    is_active: bool


class UnitConversionResponse(BaseModel):
    id: UUID
    item_id: UUID
    from_uom_id: UUID
    from_uom: str
    to_uom_id: UUID
    to_uom: str
    factor: Decimal


class ApprovedAlternateResponse(BaseModel):
    id: UUID
    item_id: UUID
    item_sku: str
    alternate_item_id: UUID
    alternate_sku: str


class CatalogSnapshotResponse(BaseModel):
    items: list[CatalogItemResponse]
    units: list[UnitOfMeasureResponse]
    conversions: list[UnitConversionResponse]
    alternates: list[ApprovedAlternateResponse]


class CreateUnitOfMeasureRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=64)
    decimal_places: int = Field(ge=0, le=3)


class CreateCatalogItemRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    inventory_path: InventoryPath
    spectrum_item_id: str | None = Field(default=None, max_length=120)
    uom_id: UUID
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)

    @model_validator(mode="after")
    def validate_accounting_identifier(self) -> "CreateCatalogItemRequest":
        if self.inventory_path == InventoryPath.SPECTRUM_MANAGED and not self.spectrum_item_id:
            raise ValueError("Spectrum-managed items require a Spectrum item ID")
        if self.inventory_path == InventoryPath.LOCAL_GENERAL_USE and self.spectrum_item_id:
            raise ValueError("Local-general-use items cannot have a Spectrum item ID")
        return self


class UpdateCatalogItemRequest(BaseModel):
    description: str = Field(min_length=1, max_length=240)
    inventory_path: InventoryPath
    spectrum_item_id: str | None = Field(default=None, max_length=120)
    reorder_point: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    is_active: bool
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_accounting_identifier(self) -> "UpdateCatalogItemRequest":
        if self.inventory_path == InventoryPath.SPECTRUM_MANAGED and not self.spectrum_item_id:
            raise ValueError("Spectrum-managed items require a Spectrum item ID")
        if self.inventory_path == InventoryPath.LOCAL_GENERAL_USE and self.spectrum_item_id:
            raise ValueError("Local-general-use items cannot have a Spectrum item ID")
        return self


class CreateUnitConversionRequest(BaseModel):
    item_id: UUID
    from_uom_id: UUID
    to_uom_id: UUID
    factor: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    reason: str = Field(min_length=3, max_length=500)


class CreateApprovedAlternateRequest(BaseModel):
    item_id: UUID
    alternate_item_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class CatalogReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)