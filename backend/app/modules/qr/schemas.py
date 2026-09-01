from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

QrTargetType = Literal["item", "location", "request"]


class CreateQrTokenRequest(BaseModel):
    target_type: QrTargetType
    target_id: UUID
    expires_in_hours: int | None = Field(default=None, ge=1, le=8760)


class QrTokenResponse(BaseModel):
    id: UUID
    target_type: QrTargetType
    target_id: UUID
    target_label: str
    target_route: str
    expires_at: str | None
    revoked_at: str | None
    last_resolved_at: str | None
    created_at: str


class CreatedQrTokenResponse(QrTokenResponse):
    token: str
    scan_path: str


class ResolveQrTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=160)


class QrResolutionResponse(BaseModel):
    target_type: QrTargetType
    target_id: UUID
    label: str
    route: str


class RevokeQrTokenRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)