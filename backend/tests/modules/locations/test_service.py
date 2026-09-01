import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import Role
from app.domain.errors import ConflictError
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.locations.schemas import CreateLocationRequest, UpdateLocationRequest
from app.modules.locations.service import LocationService
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base


@pytest.fixture
def location_context() -> tuple[Session, AuthenticatedUser]:
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
    administrator = User(
        warehouse_id=warehouse.id,
        username="administrator",
        display_name="System Administrator",
        is_active=True,
    )
    session.add(administrator)
    session.commit()
    user = AuthenticatedUser(
        id=administrator.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=administrator.username,
        display_name=administrator.display_name,
        roles=frozenset({Role.SYSTEM_ADMINISTRATOR}),
    )
    yield session, user
    session.close()


def location_payload(code: str, row: int, column: int) -> CreateLocationRequest:
    return CreateLocationRequest(
        code=code,
        zone="A",
        aisle="01",
        bay="01",
        shelf="01",
        position="01",
        pick_sequence=10,
        grid_row=row,
        grid_column=column,
    )


def test_location_rename_preserves_identity_and_updates_grid_label(
    location_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, user = location_context
    service = LocationService(session, user)
    created = service.create(location_payload("WH1-A01", 0, 0))

    updated = service.update(
        created.id,
        UpdateLocationRequest(
            **location_payload("WH1-A02", 1, 2).model_dump(),
            reason="Aisle signage corrected",
        ),
    )

    assert updated.id == created.id
    assert updated.code == "WH1-A02"
    assert (updated.grid_row, updated.grid_column) == (1, 2)


def test_grid_cell_collision_is_rejected(
    location_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, user = location_context
    service = LocationService(session, user)
    service.create(location_payload("WH1-A01", 0, 0))

    with pytest.raises(ConflictError):
        service.create(location_payload("WH1-A02", 0, 0))