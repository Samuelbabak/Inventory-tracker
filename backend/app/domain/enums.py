from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "employee"
    FOREMAN = "foreman"
    WAREHOUSE_WORKER = "warehouse_worker"
    INVENTORY_MANAGER = "inventory_manager"
    SYSTEM_ADMINISTRATOR = "system_administrator"


class InventoryPath(StrEnum):
    SPECTRUM_MANAGED = "spectrum_managed"
    LOCAL_GENERAL_USE = "local_general_use"


class RequestPriority(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"


class RequestState(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class InventoryEventType(StrEnum):
    RECEIPT = "receipt"
    GENERAL_USE_WITHDRAWAL = "general_use_withdrawal"
    MATERIAL_ISSUE = "material_issue"
    RETURN = "return"
    MOVE = "move"
    COUNT_ADJUSTMENT = "count_adjustment"
    QUARANTINE = "quarantine"
    RELEASE = "release"
    MANAGER_CORRECTION = "manager_correction"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


class OfflineCommandStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CONFLICT = "conflict"
    REJECTED = "rejected"
