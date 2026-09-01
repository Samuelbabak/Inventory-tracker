from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import OfflineCommandStatus
from app.modules.requests.schemas import MaterialRequestResponse


class CreateOfflineGrant(BaseModel):
    request_id: UUID
    device_id: str = Field(min_length=8, max_length=160)


class OfflineGrantResponse(BaseModel):
    id: UUID
    request_id: UUID
    device_id: str
    request_version: int
    expires_at: str
    snapshot: MaterialRequestResponse


class OfflineCommandInput(BaseModel):
    client_command_id: UUID
    sequence: int = Field(ge=1)
    command_type: Literal["record_pick", "handoff"]
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncOfflineCommands(BaseModel):
    grant_id: UUID
    device_id: str = Field(min_length=8, max_length=160)
    commands: list[OfflineCommandInput] = Field(min_length=1, max_length=200)


class OfflineCommandResult(BaseModel):
    client_command_id: UUID
    sequence: int
    status: OfflineCommandStatus
    result: dict[str, Any] | None


class OfflineSyncResponse(BaseModel):
    grant_id: UUID
    request_version: int
    commands: list[OfflineCommandResult]


class OfflineConflictResponse(BaseModel):
    id: UUID
    grant_id: UUID
    request_id: UUID
    request_number: str
    actor_user_id: UUID
    actor_name: str
    device_id: str
    sequence: int
    command_type: str
    payload: dict[str, Any]
    status: OfflineCommandStatus
    result: dict[str, Any] | None
    created_at: str


class ResolveOfflineConflict(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
