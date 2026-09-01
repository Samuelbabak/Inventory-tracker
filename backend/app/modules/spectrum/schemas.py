from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import OutboxStatus


class SpectrumStatusResponse(BaseModel):
    health: dict[str, str]
    capabilities: dict[str, bool]
    counts: dict[OutboxStatus, int]


class OutboxEventResponse(BaseModel):
    id: UUID
    event_type: str
    status: OutboxStatus
    attempt_count: int
    last_error: str | None
    created_at: str
    processed_at: str | None


class ReconciliationRunResponse(BaseModel):
    id: UUID
    status: str
    checked_count: int
    matched_count: int
    difference_count: int
    differences: list[dict[str, str]]
    started_at: str
    finished_at: str | None
    error: str | None
