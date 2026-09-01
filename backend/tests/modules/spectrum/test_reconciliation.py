from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import OutboxStatus, Role
from app.modules.audit.models import AuditEvent
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.spectrum.adapter import SpectrumResult
from app.modules.spectrum.models import OutboxAttempt, OutboxEvent
from app.modules.spectrum.reconciliation import ReconciliationService
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base, utc_now


class ReconciliationAdapter:
    def __init__(self, references: dict[str, str]) -> None:
        self.references = references

    def post_issue(self, payload: dict[str, Any]) -> SpectrumResult:
        del payload
        raise AssertionError("Reconciliation does not post issues")

    def find_transaction(self, business_reference: str) -> SpectrumResult | None:
        reference = self.references.get(business_reference)
        return SpectrumResult(reference) if reference else None

    def health(self) -> dict[str, str]:
        return {"status": "available"}

    def capabilities(self) -> dict[str, bool]:
        return {"reconcile": True}


@pytest.fixture
def reconciliation_context() -> tuple[Session, AuthenticatedUser]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    warehouse = Warehouse(code="WH1", name="Test Warehouse")
    session.add(warehouse)
    session.flush()
    manager = User(
        warehouse_id=warehouse.id,
        username="manager",
        display_name="Inventory Manager",
        is_active=True,
    )
    session.add(manager)
    session.commit()
    user = AuthenticatedUser(
        id=manager.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=manager.username,
        display_name=manager.display_name,
        roles=frozenset({Role.INVENTORY_MANAGER}),
    )
    yield session, user
    session.close()


def add_event(
    session: Session,
    user: AuthenticatedUser,
    business_reference: str,
    status: OutboxStatus,
    response_reference: str | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        warehouse_id=user.warehouse_id,
        event_type="material_issue",
        aggregate_id=user.id,
        payload={
            "business_reference": business_reference,
            "request_number": "MR-001",
            "sku": "WIRE-001",
        },
        status=status,
        available_at=utc_now(),
    )
    session.add(event)
    session.flush()
    if response_reference:
        session.add(
            OutboxAttempt(
                warehouse_id=user.warehouse_id,
                outbox_event_id=event.id,
                succeeded=True,
                response_reference=response_reference,
            )
        )
    session.commit()
    return event


def test_reconciliation_records_matches_and_delivery_differences(
    reconciliation_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, user = reconciliation_context
    add_event(session, user, "event-1", OutboxStatus.SUCCEEDED, "SP-1")
    add_event(session, user, "event-2", OutboxStatus.REQUIRES_REVIEW)
    adapter = ReconciliationAdapter({"event-1": "SP-1"})

    run = ReconciliationService(session, user, adapter).run()

    assert run.checked_count == 2
    assert run.matched_count == 1
    assert run.difference_count == 1
    assert run.differences[0]["kind"] == "delivery_state"
    assert session.scalar(
        select(AuditEvent).where(AuditEvent.action == "spectrum.reconciled")
    ) is not None


def test_reconciliation_records_missing_remote_transaction(
    reconciliation_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, user = reconciliation_context
    add_event(session, user, "event-3", OutboxStatus.SUCCEEDED, "SP-3")

    run = ReconciliationService(session, user, ReconciliationAdapter({})).run()

    assert run.matched_count == 0
    assert run.difference_count == 1
    assert run.differences[0]["kind"] == "missing_remote"