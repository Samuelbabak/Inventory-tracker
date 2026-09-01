import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import InventoryPath, Role
from app.domain.errors import NotFoundError
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Item, UnitOfMeasure
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.qr.models import QrToken
from app.modules.qr.service import QrService
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base
from app.platform.security.tokens import token_digest


@pytest.fixture
def qr_context() -> tuple[Session, AuthenticatedUser, Item]:
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
    manager = User(
        warehouse_id=warehouse.id,
        username="manager",
        display_name="Inventory Manager",
        is_active=True,
    )
    item = Item(
        warehouse_id=warehouse.id,
        sku="WIRE-001",
        description="Copper wire",
        inventory_path=InventoryPath.SPECTRUM_MANAGED,
        spectrum_item_id="SP-WIRE-001",
        uom_id=uom.id,
    )
    session.add_all([manager, item])
    session.commit()
    user = AuthenticatedUser(
        id=manager.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=manager.username,
        display_name=manager.display_name,
        roles=frozenset({Role.INVENTORY_MANAGER}),
    )
    yield session, user, item
    session.close()


def test_qr_token_is_hashed_and_resolves(
    qr_context: tuple[Session, AuthenticatedUser, Item],
) -> None:
    session, user, item = qr_context
    service = QrService(session, user)

    created = service.create("item", item.id, None)
    stored = session.scalar(select(QrToken).where(QrToken.id == created.id))
    resolved = service.resolve(created.token)

    assert stored is not None
    assert stored.token_hash == token_digest(created.token)
    assert stored.token_hash != created.token
    assert created.scan_path == f"/scan#{created.token}"
    assert resolved.route == "/inventory?search=WIRE-001"
    assert stored.last_resolved_at is not None


def test_revoked_qr_token_cannot_resolve(
    qr_context: tuple[Session, AuthenticatedUser, Item],
) -> None:
    session, user, item = qr_context
    service = QrService(session, user)
    created = service.create("item", item.id, 24)

    revoked = service.revoke(created.id, "Shelf label replaced")

    assert revoked.revoked_at is not None
    with pytest.raises(NotFoundError):
        service.resolve(created.token)
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "qr.revoked"))
    assert audit is not None
    assert audit.reason == "Shelf label replaced"