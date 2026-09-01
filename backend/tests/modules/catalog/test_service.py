from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import InventoryPath, Role
from app.domain.errors import ConflictError
from app.modules.catalog.models import Item, UnitOfMeasure
from app.modules.catalog.schemas import (
    CreateCatalogItemRequest,
    UpdateCatalogItemRequest,
)
from app.modules.catalog.service import CatalogService
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.inventory.models import StockPosition
from app.modules.locations.models import Location
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base


@pytest.fixture
def catalog_context() -> tuple[Session, AuthenticatedUser, UnitOfMeasure, Location]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    warehouse = Warehouse(code="WH1", name="Test Warehouse")
    unit = UnitOfMeasure(code="EA", name="Each", decimal_places=0)
    session.add_all([warehouse, unit])
    session.flush()
    manager = User(
        warehouse_id=warehouse.id,
        username="manager",
        display_name="Inventory Manager",
        is_active=True,
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
    session.add_all([manager, location])
    session.commit()
    user = AuthenticatedUser(
        id=manager.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=manager.username,
        display_name=manager.display_name,
        roles=frozenset({Role.INVENTORY_MANAGER}),
    )
    yield session, user, unit, location
    session.close()


def test_create_item_and_snapshot(
    catalog_context: tuple[Session, AuthenticatedUser, UnitOfMeasure, Location],
) -> None:
    session, user, unit, _ = catalog_context
    service = CatalogService(session, user)

    created = service.create_item(
        CreateCatalogItemRequest(
            sku="tape-001",
            description="Electrical tape",
            inventory_path=InventoryPath.LOCAL_GENERAL_USE,
            uom_id=unit.id,
            reorder_point=Decimal("12"),
        )
    )
    snapshot = service.snapshot()

    assert created.sku == "TAPE-001"
    assert snapshot.items[0].uom == "EA"


def test_accounting_path_change_is_blocked_while_stock_exists(
    catalog_context: tuple[Session, AuthenticatedUser, UnitOfMeasure, Location],
) -> None:
    session, user, unit, location = catalog_context
    item = Item(
        warehouse_id=user.warehouse_id,
        sku="TAPE-002",
        description="Electrical tape",
        inventory_path=InventoryPath.LOCAL_GENERAL_USE,
        uom_id=unit.id,
    )
    session.add(item)
    session.flush()
    session.add(
        StockPosition(
            warehouse_id=user.warehouse_id,
            item_id=item.id,
            location_id=location.id,
            on_hand=Decimal("1"),
        )
    )
    session.commit()

    with pytest.raises(ConflictError):
        CatalogService(session, user).update_item(
            item.id,
            UpdateCatalogItemRequest(
                description=item.description,
                inventory_path=InventoryPath.SPECTRUM_MANAGED,
                spectrum_item_id="SP-TAPE-002",
                reorder_point=Decimal("0"),
                is_active=True,
                reason="Accounting classification correction",
            ),
        )