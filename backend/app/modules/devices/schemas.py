from uuid import UUID

from pydantic import BaseModel, Field


class EnrollDeviceRequest(BaseModel):
    device_identifier: str = Field(min_length=8, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)


class DeviceResponse(BaseModel):
    id: UUID
    device_identifier: str
    display_name: str
    enrolled_by_user_id: UUID | None
    last_seen_at: str
    revoked_at: str | None


class RevokeDeviceRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)