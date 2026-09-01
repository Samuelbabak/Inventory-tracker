from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import Role
from app.domain.errors import ConflictError
from app.modules.identity.admin_service import UserAdministrationService
from app.modules.identity.models import RoleAssignment, User, UserSession
from app.modules.identity.schemas import CreateUserRequest, UpdateUserRequest
from app.modules.identity.service import AuthenticatedUser
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base, utc_now


@pytest.fixture
def identity_context() -> tuple[Session, AuthenticatedUser]:
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
    session.flush()
    session.add(
        RoleAssignment(
            warehouse_id=warehouse.id,
            user_id=administrator.id,
            role=Role.SYSTEM_ADMINISTRATOR,
        )
    )
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


def test_role_change_invalidates_existing_sessions(
    identity_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, administrator = identity_context
    service = UserAdministrationService(session, administrator)
    worker = service.create(
        CreateUserRequest(
            username="worker",
            display_name="Warehouse Worker",
            password="temporary-password",
            roles=[Role.WAREHOUSE_WORKER],
        )
    )
    session.add(
        UserSession(
            warehouse_id=administrator.warehouse_id,
            user_id=worker.id,
            token_hash="a" * 64,
            csrf_hash="b" * 64,
            expires_at=utc_now() + timedelta(hours=12),
        )
    )
    session.commit()

    updated = service.update(
        worker.id,
        UpdateUserRequest(
            display_name=worker.display_name,
            is_active=True,
            roles=[Role.INVENTORY_MANAGER],
            reason="Promoted to inventory manager",
        ),
    )

    assert updated.roles == [Role.INVENTORY_MANAGER]
    assert session.scalar(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == worker.id)
    ) == 0


def test_administrator_cannot_remove_own_access(
    identity_context: tuple[Session, AuthenticatedUser],
) -> None:
    session, administrator = identity_context

    with pytest.raises(ConflictError):
        UserAdministrationService(session, administrator).update(
            administrator.id,
            UpdateUserRequest(
                display_name=administrator.display_name,
                is_active=True,
                roles=[Role.INVENTORY_MANAGER],
                reason="Remove administrator role",
            ),
        )