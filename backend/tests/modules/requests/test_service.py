from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import InventoryPath, RequestPriority, RequestState, Role
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import ApprovedAlternate, Item, UnitOfMeasure
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.models import InventoryEvent, StockPosition
from app.modules.locations.models import Location
from app.modules.notifications.models import Notification
from app.modules.recipients.models import EmployeeRecipient
from app.modules.requests.schemas import CreateMaterialRequest, RequestLineInput
from app.modules.requests.service import RequestService
from app.modules.spectrum.models import OutboxEvent
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base


@pytest.fixture
def request_context() -> tuple[
    Session,
    AuthenticatedUser,
    EmployeeRecipient,
    Item,
    Item,
    StockPosition,
    StockPosition,
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    warehouse = Warehouse(code="WH1", name="Test Warehouse")
    uom = UnitOfMeasure(code="EA", name="Each", decimal_places=0)
    session.add_all([warehouse, uom])
    session.flush()
    worker = User(
        warehouse_id=warehouse.id,
        username="worker",
        display_name="Warehouse Worker",
        is_active=True,
    )
    recipient = EmployeeRecipient(
        warehouse_id=warehouse.id,
        employee_number="E-200",
        display_name="Site Foreman",
    )
    spectrum_item = Item(
        warehouse_id=warehouse.id,
        sku="WIRE-001",
        description="Copper wire",
        inventory_path=InventoryPath.SPECTRUM_MANAGED,
        spectrum_item_id="SP-WIRE-001",
        uom_id=uom.id,
    )
    local_item = Item(
        warehouse_id=warehouse.id,
        sku="TAPE-001",
        description="Electrical tape",
        inventory_path=InventoryPath.LOCAL_GENERAL_USE,
        uom_id=uom.id,
    )
    location = Location(
        warehouse_id=warehouse.id,
        code="WH1-A01-B01-S01-P01",
        zone="A",
        aisle="01",
        bay="01",
        shelf="01",
        position="01",
        pick_sequence=1,
    )
    session.add_all([worker, recipient, spectrum_item, local_item, location])
    session.flush()
    spectrum_position = StockPosition(
        warehouse_id=warehouse.id,
        item_id=spectrum_item.id,
        location_id=location.id,
        on_hand=Decimal("10"),
    )
    local_position = StockPosition(
        warehouse_id=warehouse.id,
        item_id=local_item.id,
        location_id=location.id,
        on_hand=Decimal("10"),
    )
    session.add_all([spectrum_position, local_position])
    session.commit()
    user = AuthenticatedUser(
        id=worker.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=worker.username,
        display_name=worker.display_name,
        roles=frozenset({Role.WAREHOUSE_WORKER}),
    )
    yield (
        session,
        user,
        recipient,
        spectrum_item,
        local_item,
        spectrum_position,
        local_position,
    )
    session.close()


def test_partial_handoff_writes_ledger_and_only_spectrum_outbox(
    request_context: tuple[
        Session,
        AuthenticatedUser,
        EmployeeRecipient,
        Item,
        Item,
        StockPosition,
        StockPosition,
    ],
) -> None:
    (
        session,
        user,
        recipient,
        spectrum_item,
        local_item,
        spectrum_position,
        local_position,
    ) = request_context
    service = RequestService(session, user)
    created = service.create(
        CreateMaterialRequest(
            recipient_id=recipient.id,
            priority=RequestPriority.URGENT,
            urgent_reason="Crew is waiting",
            job_number="JOB-4102",
            lines=[
                RequestLineInput(item_id=spectrum_item.id, quantity=Decimal("16")),
                RequestLineInput(item_id=local_item.id, quantity=Decimal("2")),
            ],
        )
    )

    spectrum_line = next(line for line in created.lines if line.item_id == spectrum_item.id)
    assert spectrum_line.allocated_qty == Decimal("10")
    assert spectrum_line.backordered_qty == Decimal("6")
    assert created.state == RequestState.SUBMITTED

    claimed = service.claim(created.id)
    assert claimed.claimed_by_name == user.display_name
    for line in claimed.lines:
        for allocation in line.allocations:
            picked = service.record_pick(
                claimed.id,
                allocation_id=allocation.id,
                quantity=allocation.quantity,
                scanned_location_code=allocation.location_code,
                scanned_sku=line.sku,
                shortage_reason=None,
            )

    assert picked.state == RequestState.READY
    completed_batch = service.handoff(created.id)

    assert completed_batch.state == RequestState.PARTIALLY_FULFILLED
    assert spectrum_position.on_hand == Decimal("0")
    assert local_position.on_hand == Decimal("8")
    assert session.scalar(select(func.count()).select_from(InventoryEvent)) == 2
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    outbox = session.scalar(select(OutboxEvent))
    assert outbox is not None
    assert outbox.payload["job_number"] == "JOB-4102"


def test_manager_reallocation_moves_open_stock_and_notifies_both_requests(
    request_context: tuple[
        Session,
        AuthenticatedUser,
        EmployeeRecipient,
        Item,
        Item,
        StockPosition,
        StockPosition,
    ],
) -> None:
    session, worker, recipient, _, local_item, _, _ = request_context
    service = RequestService(session, worker)
    source = service.create(
        CreateMaterialRequest(
            recipient_id=recipient.id,
            lines=[RequestLineInput(item_id=local_item.id, quantity=Decimal("8"))],
        )
    )
    target = service.create(
        CreateMaterialRequest(
            recipient_id=recipient.id,
            lines=[RequestLineInput(item_id=local_item.id, quantity=Decimal("6"))],
        )
    )
    manager = AuthenticatedUser(
        id=worker.id,
        warehouse_id=worker.warehouse_id,
        warehouse_code=worker.warehouse_code,
        username=worker.username,
        display_name=worker.display_name,
        roles=frozenset({Role.INVENTORY_MANAGER}),
    )

    result = RequestService(session, manager).reallocate(
        source_allocation_id=source.lines[0].allocations[0].id,
        target_request_line_id=target.lines[0].id,
        quantity=Decimal("3"),
        reason="Crew priority changed",
    )

    assert result.source_request.lines[0].allocated_qty == Decimal("5")
    assert result.source_request.lines[0].backordered_qty == Decimal("3")
    assert result.target_request.lines[0].allocated_qty == Decimal("5")
    assert result.target_request.lines[0].backordered_qty == Decimal("1")
    assert session.scalar(select(func.count()).select_from(Notification)) == 2
    assert session.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "allocation.reallocated"
        )
    ) == 1


def test_approved_substitute_is_the_item_issued_and_sent_to_spectrum(
    request_context: tuple[
        Session,
        AuthenticatedUser,
        EmployeeRecipient,
        Item,
        Item,
        StockPosition,
        StockPosition,
    ],
) -> None:
    session, worker, recipient, requested_item, _, requested_position, _ = request_context
    location = session.scalar(select(Location))
    assert location is not None
    alternate = Item(
        warehouse_id=worker.warehouse_id,
        sku="WIRE-ALT-001",
        description="Approved alternate copper wire",
        inventory_path=InventoryPath.SPECTRUM_MANAGED,
        spectrum_item_id="SP-WIRE-ALT-001",
        uom_id=requested_item.uom_id,
    )
    session.add(alternate)
    session.flush()
    alternate_position = StockPosition(
        warehouse_id=worker.warehouse_id,
        item_id=alternate.id,
        location_id=location.id,
        on_hand=Decimal("5"),
    )
    session.add_all(
        [
            alternate_position,
            ApprovedAlternate(
                warehouse_id=worker.warehouse_id,
                item_id=requested_item.id,
                alternate_item_id=alternate.id,
            ),
        ]
    )
    session.commit()
    service = RequestService(session, worker)
    created = service.create(
        CreateMaterialRequest(
            recipient_id=recipient.id,
            job_number="JOB-4102",
            lines=[RequestLineInput(item_id=requested_item.id, quantity=Decimal("4"))],
        )
    )
    claimed = service.claim(created.id)

    candidates = service.list_substitute_candidates(
        created.id, claimed.lines[0].allocations[0].id
    )
    assert len(candidates) == 1
    assert candidates[0].stock_position_id == alternate_position.id
    assert candidates[0].available_qty == Decimal("5")

    substituted = service.substitute(
        created.id,
        allocation_id=claimed.lines[0].allocations[0].id,
        alternate_stock_position_id=alternate_position.id,
        quantity=Decimal("4"),
        reason="Requested reel is damaged",
    )
    replacement = next(
        allocation for allocation in substituted.lines[0].allocations
        if allocation.is_substitute
    )
    assert replacement.fulfillment_uom == "EA"
    picked = service.record_pick(
        created.id,
        allocation_id=replacement.id,
        quantity=Decimal("4"),
        scanned_location_code=replacement.location_code,
        scanned_sku=alternate.sku,
        shortage_reason=None,
    )
    assert picked.state == RequestState.READY

    service.handoff(created.id)

    assert requested_position.on_hand == Decimal("10")
    assert alternate_position.on_hand == Decimal("1")
    issued_event = session.scalar(select(InventoryEvent))
    assert issued_event is not None
    assert issued_event.item_id == alternate.id
    outbox = session.scalar(select(OutboxEvent))
    assert outbox is not None
    assert outbox.payload["spectrum_item_id"] == alternate.spectrum_item_id
