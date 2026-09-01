from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.errors import ConflictError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.devices.models import Device
from app.modules.devices.schemas import DeviceResponse
from app.modules.identity.service import AuthenticatedUser
from app.modules.offline.models import OfflineGrant
from app.platform.database.base import utc_now


class DeviceService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def enroll(self, device_identifier: str, display_name: str) -> DeviceResponse:
        device = self.session.scalar(
            select(Device)
            .where(
                Device.warehouse_id == self.user.warehouse_id,
                Device.device_identifier == device_identifier,
            )
            .with_for_update()
        )
        now = utc_now()
        if device is not None and device.revoked_at is not None:
            raise ConflictError("This device has been revoked by an administrator")
        if device is None:
            device = Device(
                warehouse_id=self.user.warehouse_id,
                device_identifier=device_identifier,
                display_name=display_name,
                enrolled_by_user_id=self.user.id,
                last_seen_at=now,
            )
            self.session.add(device)
            self.session.flush()
            record_audit(
                self.session,
                warehouse_id=self.user.warehouse_id,
                actor_user_id=self.user.id,
                action="device.enrolled",
                entity_type="device",
                entity_id=device.id,
                changes={"display_name": display_name},
            )
        else:
            device.display_name = display_name
            device.last_seen_at = now
        self.session.commit()
        return self._response(device)

    def list(self) -> list[DeviceResponse]:
        devices = self.session.scalars(
            select(Device)
            .where(Device.warehouse_id == self.user.warehouse_id)
            .order_by(Device.revoked_at.nulls_first(), Device.last_seen_at.desc())
        ).all()
        return [self._response(device) for device in devices]

    def revoke(self, device_id: UUID, reason: str) -> DeviceResponse:
        device = self.session.scalar(
            select(Device)
            .where(
                Device.id == device_id,
                Device.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if device is None:
            raise NotFoundError("Device not found")
        if device.revoked_at is None:
            now = utc_now()
            device.revoked_at = now
            self.session.execute(
                update(OfflineGrant)
                .where(
                    OfflineGrant.warehouse_id == self.user.warehouse_id,
                    OfflineGrant.device_id == device.device_identifier,
                    OfflineGrant.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            record_audit(
                self.session,
                warehouse_id=self.user.warehouse_id,
                actor_user_id=self.user.id,
                action="device.revoked",
                entity_type="device",
                entity_id=device.id,
                changes={"device_identifier": device.device_identifier},
                reason=reason,
            )
            self.session.commit()
        return self._response(device)

    def assert_active(self, device_identifier: str) -> Device:
        device = self.session.scalar(
            select(Device).where(
                Device.warehouse_id == self.user.warehouse_id,
                Device.device_identifier == device_identifier,
                Device.revoked_at.is_(None),
            )
        )
        if device is None:
            raise NotFoundError("Enrolled device not found")
        device.last_seen_at = utc_now()
        return device

    @staticmethod
    def _response(device: Device) -> DeviceResponse:
        return DeviceResponse(
            id=device.id,
            device_identifier=device.device_identifier,
            display_name=device.display_name,
            enrolled_by_user_id=device.enrolled_by_user_id,
            last_seen_at=device.last_seen_at.isoformat(),
            revoked_at=device.revoked_at.isoformat() if device.revoked_at else None,
        )