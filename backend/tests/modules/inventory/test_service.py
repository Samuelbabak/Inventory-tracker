from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import InventoryPath, Role
from app.domain.errors import ConflictError, PermissionDeniedError
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Item, UnitOfMeasure
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.models import InventoryEvent, StockPosition
from app.modules.inventory.service import InventoryService
from app.modules.locations.models import Location
from app.modules.recipients.models import EmployeeRecipient
from app.modules.spectrum.models import OutboxEvent
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base


@pytest.fixture
def inventory_context() -> tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient]:
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
    user = User(
        warehouse_id=warehouse.id,
        username="manager",
        display_name="Inventory Manager",
        is_active=True,
    )
    recipient = EmployeeRecipient(
        warehouse_id=warehouse.id,
        employee_number="E-100",
        display_name="Test Recipient",
        linked_user_id=user.id,
    )
    item = Item(
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
    session.add_all([user, recipient, item, location])
    session.flush()
    position = StockPosition(
        warehouse_id=warehouse.id,
        item_id=item.id,
        location_id=location.id,
        on_hand=Decimal("20"),
    )
    session.add(position)
    session.commit()
    context = AuthenticatedUser(
        id=user.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=user.username,
        display_name=user.display_name,
        roles=frozenset({Role.INVENTORY_MANAGER}),
    )
    yield session, context, position, recipient
    session.close()


def test_general_use_withdrawal_is_atomic_and_never_enters_outbox(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, position, recipient = inventory_context

    result = InventoryService(session, user).withdraw_general_use(
        stock_position_id=position.id,
        recipient_id=recipient.id,
        quantity=Decimal("3"),
        note="Crew supplies",
    )

    assert result.on_hand == Decimal("17")
    assert session.scalar(select(InventoryEvent)) is not None
    assert session.scalar(select(AuditEvent)) is not None
    assert session.scalar(select(OutboxEvent)) is None


def test_inventory_projection_keeps_demand_concepts_separate(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, position, _ = inventory_context

    inventory = InventoryService(session, user).list_inventory()

    assert len(inventory) == 1
    assert inventory[0].on_hand == Decimal("20")
    assert inventory[0].free_to_promise == Decimal("20")
    assert inventory[0].reserved_demand == Decimal("0")
    assert inventory[0].locations[0].stock_position_id == position.id


def test_inventory_search_matches_location_code(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, _, _ = inventory_context

    inventory = InventoryService(session, user).list_inventory("A01-B01")

    assert [item.sku for item in inventory] == ["TAPE-001"]


def test_employee_cannot_withdraw_for_another_recipient(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, position, _ = inventory_context
    other_recipient = EmployeeRecipient(
        warehouse_id=user.warehouse_id,
        employee_number="E-200",
        display_name="Other Recipient",
    )
    session.add(other_recipient)
    session.commit()
    employee = AuthenticatedUser(
        id=user.id,
        warehouse_id=user.warehouse_id,
        warehouse_code=user.warehouse_code,
        username=user.username,
        display_name=user.display_name,
        roles=frozenset({Role.EMPLOYEE}),
    )

    with pytest.raises(PermissionDeniedError):
        InventoryService(session, employee).withdraw_general_use(
            stock_position_id=position.id,
            recipient_id=other_recipient.id,
            quantity=Decimal("1"),
            note=None,
        )

    assert position.on_hand == Decimal("20")


def test_return_quarantine_and_release_preserve_physical_stock_accounting(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, position, _ = inventory_context
    service = InventoryService(session, user)

    service.return_stock(
        stock_position_id=position.id,
        quantity=Decimal("3"),
        condition="quarantined",
        reason="Returned damaged from site",
    )
    service.release(
        stock_position_id=position.id,
        quantity=Decimal("2"),
        reason="Inspection passed",
    )
    service.quarantine(
        stock_position_id=position.id,
        quantity=Decimal("4"),
        reason="Packaging damage",
    )

    assert position.on_hand == Decimal("23")
    assert position.quarantined_qty == Decimal("5")
    assert service.list_inventory()[0].on_hand == Decimal("18")
    assert session.scalar(select(func.count()).select_from(InventoryEvent)) == 3


def test_spectrum_receipt_is_blocked_without_posting_capability(
    inventory_context: tuple[Session, AuthenticatedUser, StockPosition, EmployeeRecipient],
) -> None:
    session, user, position, _ = inventory_context
    item = session.get(Item, position.item_id)
    assert item is not None
    item.inventory_path = InventoryPath.SPECTRUM_MANAGED
    item.spectrum_item_id = "SP-TAPE-001"
    session.commit()

    with pytest.raises(ConflictError, match="post receipt is not enabled"):
        InventoryService(session, user).receive(
            stock_position_id=position.id,
            quantity=Decimal("1"),
            reason="Vendor receipt",
        )

    assert position.on_hand == Decimal("20")
