from datetime import timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.modules.audit.service import record_audit
from app.modules.catalog.models import Item
from app.modules.identity.service import AuthenticatedUser
from app.modules.locations.models import Location
from app.modules.qr.models import QrToken
from app.modules.qr.schemas import (
    CreatedQrTokenResponse,
    QrResolutionResponse,
    QrTargetType,
    QrTokenResponse,
)
from app.modules.requests.models import MaterialRequest
from app.platform.database.base import utc_now
from app.platform.security.tokens import new_opaque_token, token_digest


class QrService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def create(
        self,
        target_type: QrTargetType,
        target_id: UUID,
        expires_in_hours: int | None,
    ) -> CreatedQrTokenResponse:
        target_label, target_route = self._target_details(target_type, target_id)
        raw_token = new_opaque_token()
        record = QrToken(
            warehouse_id=self.user.warehouse_id,
            token_hash=token_digest(raw_token),
            target_type=target_type,
            target_id=target_id,
            created_by_user_id=self.user.id,
            expires_at=(
                utc_now() + timedelta(hours=expires_in_hours)
                if expires_in_hours is not None
                else None
            ),
        )
        self.session.add(record)
        self.session.flush()
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="qr.created",
            entity_type="qr_token",
            entity_id=record.id,
            changes={
                "target_type": target_type,
                "target_id": str(target_id),
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            },
        )
        self.session.commit()
        base = self._response(record, target_label, target_route)
        return CreatedQrTokenResponse(
            **base.model_dump(),
            token=raw_token,
            scan_path=f"/scan#{raw_token}",
        )

    def list(self, limit: int = 200) -> list[QrTokenResponse]:
        records = self.session.scalars(
            select(QrToken)
            .where(QrToken.warehouse_id == self.user.warehouse_id)
            .order_by(QrToken.created_at.desc())
            .limit(limit)
        ).all()
        responses: list[QrTokenResponse] = []
        for record in records:
            try:
                target_label, target_route = self._target_details(
                    record.target_type, record.target_id
                )
            except NotFoundError:
                target_label = "Unavailable target"
                target_route = "/"
            responses.append(self._response(record, target_label, target_route))
        return responses

    def resolve(self, raw_token: str) -> QrResolutionResponse:
        now = utc_now()
        record = self.session.scalar(
            select(QrToken)
            .where(
                QrToken.warehouse_id == self.user.warehouse_id,
                QrToken.token_hash == token_digest(raw_token),
                QrToken.revoked_at.is_(None),
                or_(QrToken.expires_at.is_(None), QrToken.expires_at > now),
            )
            .with_for_update()
        )
        if record is None:
            raise NotFoundError("Active QR label not found")
        target_label, target_route = self._target_details(
            record.target_type, record.target_id
        )
        record.last_resolved_at = now
        self.session.commit()
        return QrResolutionResponse(
            target_type=record.target_type,
            target_id=record.target_id,
            label=target_label,
            route=target_route,
        )

    def revoke(self, token_id: UUID, reason: str) -> QrTokenResponse:
        record = self.session.scalar(
            select(QrToken)
            .where(
                QrToken.id == token_id,
                QrToken.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if record is None:
            raise NotFoundError("QR label not found")
        target_label, target_route = self._target_details(
            record.target_type, record.target_id
        )
        if record.revoked_at is None:
            record.revoked_at = utc_now()
            record_audit(
                self.session,
                warehouse_id=self.user.warehouse_id,
                actor_user_id=self.user.id,
                action="qr.revoked",
                entity_type="qr_token",
                entity_id=record.id,
                changes={
                    "target_type": record.target_type,
                    "target_id": str(record.target_id),
                },
                reason=reason,
            )
            self.session.commit()
        return self._response(record, target_label, target_route)

    def _target_details(
        self, target_type: QrTargetType, target_id: UUID
    ) -> tuple[str, str]:
        if target_type == "item":
            item = self.session.scalar(
                select(Item).where(
                    Item.id == target_id,
                    Item.warehouse_id == self.user.warehouse_id,
                )
            )
            if item is not None:
                return f"{item.sku} / {item.description}", f"/inventory?search={item.sku}"
        elif target_type == "location":
            location = self.session.scalar(
                select(Location).where(
                    Location.id == target_id,
                    Location.warehouse_id == self.user.warehouse_id,
                )
            )
            if location is not None:
                return location.code, f"/inventory?search={location.code}"
        else:
            request = self.session.scalar(
                select(MaterialRequest).where(
                    MaterialRequest.id == target_id,
                    MaterialRequest.warehouse_id == self.user.warehouse_id,
                )
            )
            if request is not None:
                return request.request_number, f"/requests/{request.id}"
        raise NotFoundError("QR target not found")

    @staticmethod
    def _response(
        record: QrToken, target_label: str, target_route: str
    ) -> QrTokenResponse:
        return QrTokenResponse(
            id=record.id,
            target_type=record.target_type,
            target_id=record.target_id,
            target_label=target_label,
            target_route=target_route,
            expires_at=record.expires_at.isoformat() if record.expires_at else None,
            revoked_at=record.revoked_at.isoformat() if record.revoked_at else None,
            last_resolved_at=(
                record.last_resolved_at.isoformat() if record.last_resolved_at else None
            ),
            created_at=record.created_at.isoformat(),
        )