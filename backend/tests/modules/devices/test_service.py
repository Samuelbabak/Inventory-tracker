from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.domain.enums import Role
from app.domain.errors import ConflictError, NotFoundError
from app.modules.audit.models import AuditEvent
from app.modules.devices.models import Device
from app.modules.devices.service import DeviceService
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.offline.models import OfflineGrant
from app.modules.recipients.models import EmployeeRecipient
from app.modules.requests.models import MaterialRequest
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import Base, utc_now


@pytest.fixture
def device_context() -> tuple[Session, AuthenticatedUser, MaterialRequest]:
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
    recipient = EmployeeRecipient(
        warehouse_id=warehouse.id,
        employee_number="E-001",
        display_name="Test Recipient",
    )
    session.add(recipient)
    session.flush()
    request = MaterialRequest(
        warehouse_id=warehouse.id,
        request_number="MR-TEST-001",
        creator_user_id=administrator.id,
        recipient_id=recipient.id,
    )
    session.add(request)
    session.commit()
    user = AuthenticatedUser(
        id=administrator.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=administrator.username,
        display_name=administrator.display_name,
        roles=frozenset({Role.SYSTEM_ADMINISTRATOR}),
    )
    yield session, user, request
    session.close()


def test_enrollment_is_idempotent(
    device_context: tuple[Session, AuthenticatedUser, MaterialRequest],
) -> None:
    session, user, _ = device_context
    service = DeviceService(session, user)

    first = service.enroll("device-identifier-001", "Receiving tablet")
    second = service.enroll("device-identifier-001", "Receiving tablet 2")

    assert first.id == second.id
    assert second.display_name == "Receiving tablet 2"
    assert len(session.scalars(select(Device)).all()) == 1


def test_revocation_invalidates_grants_and_is_audited(
    device_context: tuple[Session, AuthenticatedUser, MaterialRequest],
) -> None:
    session, user, request = device_context
    service = DeviceService(session, user)
    device = service.enroll("device-identifier-002", "Pick cart")
    grant = OfflineGrant(
        warehouse_id=user.warehouse_id,
        user_id=user.id,
        request_id=request.id,
        device_id=device.device_identifier,
        request_version=1,
        expires_at=utc_now() + timedelta(hours=12),
    )
    session.add(grant)
    session.commit()

    revoked = service.revoke(device.id, "Tablet reported missing")

    assert revoked.revoked_at is not None
    session.refresh(grant)
    assert grant.revoked_at is not None
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "device.revoked"))
    assert audit is not None
    assert audit.reason == "Tablet reported missing"
    with pytest.raises(NotFoundError):
        service.assert_active(device.device_identifier)
    with pytest.raises(ConflictError):
        service.enroll(device.device_identifier, "Attempted reactivation")