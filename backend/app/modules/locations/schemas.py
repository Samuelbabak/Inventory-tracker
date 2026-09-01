from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class LocationResponse(BaseModel):
    id: UUID
    code: str
    zone: str
    aisle: str
    bay: str
    shelf: str
    position: str
    pick_sequence: int
    is_staging: bool
    grid_row: int | None
    grid_column: int | None


class CreateLocationRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    zone: str = Field(min_length=1, max_length=40)
    aisle: str = Field(min_length=1, max_length=40)
    bay: str = Field(min_length=1, max_length=40)
    shelf: str = Field(min_length=1, max_length=40)
    position: str = Field(min_length=1, max_length=40)
    pick_sequence: int = Field(ge=0, le=1_000_000)
    is_staging: bool = False
    grid_row: int | None = Field(default=None, ge=0, le=999)
    grid_column: int | None = Field(default=None, ge=0, le=999)

    @model_validator(mode="after")
    def require_complete_grid_coordinate(self) -> "CreateLocationRequest":
        if (self.grid_row is None) != (self.grid_column is None):
            raise ValueError("Grid row and column must be supplied together")
        return self


class UpdateLocationRequest(CreateLocationRequest):
    reason: str = Field(min_length=3, max_length=500)
