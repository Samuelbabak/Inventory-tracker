from datetime import timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import OfflineCommandStatus, RequestState, Role
from app.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)
from app.modules.audit.service import record_audit
from app.modules.devices.service import DeviceService
from app.modules.identity.models import User
from app.modules.identity.service import AuthenticatedUser
from app.modules.notifications.service import notify_user
from app.modules.offline.models import OfflineCommand, OfflineGrant
from app.modules.offline.schemas import (
    OfflineCommandInput,
    OfflineCommandResult,
    OfflineConflictResponse,
    OfflineGrantResponse,
    OfflineSyncResponse,
)
from app.modules.requests.models import MaterialRequest
from app.modules.requests.schemas import RecordPickRequest
from app.modules.requests.service import RequestService
from app.platform.database.base import utc_now

OFFLINE_STATES = (
    RequestState.CLAIMED,
    RequestState.IN_PROGRESS,
    RequestState.READY,
)


class OfflineService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def create_grant(self, request_id: UUID, device_id: str) -> OfflineGrantResponse:
        DeviceService(self.session, self.user).assert_active(device_id)
        material_request = self.session.scalar(
            select(MaterialRequest)
            .where(
                MaterialRequest.id == request_id,
                MaterialRequest.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if material_request is None:
            raise NotFoundError("Request not found")
        if (
            material_request.claimed_by_user_id != self.user.id
            or material_request.state not in OFFLINE_STATES
        ):
            raise ConflictError("Only a request claimed by this worker can go offline")
        grant = OfflineGrant(
            warehouse_id=self.user.warehouse_id,
            user_id=self.user.id,
            request_id=material_request.id,
            device_id=device_id,
            request_version=material_request.version,
            expires_at=utc_now() + timedelta(hours=12),
        )
        self.session.add(grant)
        self.session.commit()
        return OfflineGrantResponse(
            id=grant.id,
            request_id=grant.request_id,
            device_id=grant.device_id,
            request_version=grant.request_version,
            expires_at=grant.expires_at.isoformat(),
            snapshot=RequestService(self.session, self.user).get(grant.request_id),
        )

    def list_conflicts(self, limit: int = 100) -> list[OfflineConflictResponse]:
        self._assert_manager()
        rows = self.session.execute(
            select(
                OfflineCommand,
                OfflineGrant,
                MaterialRequest.request_number,
                User.display_name,
            )
            .join(OfflineGrant, OfflineGrant.id == OfflineCommand.grant_id)
            .join(MaterialRequest, MaterialRequest.id == OfflineGrant.request_id)
            .join(User, User.id == OfflineGrant.user_id)
            .where(
                OfflineCommand.warehouse_id == self.user.warehouse_id,
                OfflineCommand.status == OfflineCommandStatus.CONFLICT,
            )
            .order_by(OfflineCommand.created_at.desc())
            .limit(limit)
        ).all()
        return [
            self._conflict_response(command, grant, request_number, actor_name)
            for command, grant, request_number, actor_name in rows
        ]

    def reject_conflict(
        self, command_id: UUID, reason: str
    ) -> OfflineConflictResponse:
        self._assert_manager()
        row = self.session.execute(
            select(
                OfflineCommand,
                OfflineGrant,
                MaterialRequest.request_number,
                User.display_name,
            )
            .join(OfflineGrant, OfflineGrant.id == OfflineCommand.grant_id)
            .join(MaterialRequest, MaterialRequest.id == OfflineGrant.request_id)
            .join(User, User.id == OfflineGrant.user_id)
            .where(
                OfflineCommand.id == command_id,
                OfflineCommand.warehouse_id == self.user.warehouse_id,
                OfflineCommand.status == OfflineCommandStatus.CONFLICT,
            )
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise NotFoundError("Reviewable offline conflict not found")
        command, grant, request_number, actor_name = row
        command.status = OfflineCommandStatus.REJECTED
        command.result = {
            **(command.result or {}),
            "resolution": {
                "action": "rejected",
                "reason": reason,
                "resolved_by_user_id": str(self.user.id),
            },
        }
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="offline.conflict_rejected",
            entity_type="offline_command",
            entity_id=command.id,
            changes={
                "status": OfflineCommandStatus.REJECTED.value,
                "request_id": str(grant.request_id),
            },
            reason=reason,
        )
        notify_user(
            self.session,
            warehouse_id=self.user.warehouse_id,
            user_id=grant.user_id,
            title=f"{request_number} offline conflict reviewed",
            message=f"The {command.command_type.replace('_', ' ')} command was rejected: {reason}",
            entity_type="material_request",
            entity_id=grant.request_id,
        )
        self.session.commit()
        return self._conflict_response(command, grant, request_number, actor_name)

    def sync(
        self,
        *,
        grant_id: UUID,
        device_id: str,
        commands: list[OfflineCommandInput],
    ) -> OfflineSyncResponse:
        results: list[OfflineCommandResult] = []
        self._locked_grant(grant_id, device_id)
        ordered_commands = sorted(commands, key=lambda command: command.sequence)
        if len({command.sequence for command in ordered_commands}) != len(ordered_commands):
            raise ConflictError("Offline command sequences must be unique")

        for command in ordered_commands:
            existing = self.session.scalar(
                select(OfflineCommand).where(
                    OfflineCommand.warehouse_id == self.user.warehouse_id,
                    OfflineCommand.client_command_id == command.client_command_id,
                )
            )
            if existing:
                results.append(self._command_response(existing))
                continue
            grant = self._locked_grant(grant_id, device_id)
            last_sequence = self.session.scalar(
                select(func.coalesce(func.max(OfflineCommand.sequence), 0)).where(
                    OfflineCommand.grant_id == grant.id
                )
            )
            if command.sequence != last_sequence + 1:
                raise ConflictError(
                    f"Expected offline command sequence {last_sequence + 1}"
                )
            material_request = self.session.get(MaterialRequest, grant.request_id)
            if material_request is None:
                raise NotFoundError("Request not found")
            if material_request.version != grant.request_version:
                return self._record_conflict(
                    grant,
                    command,
                    "Request changed after the offline snapshot was issued",
                    results,
                )

            try:
                response = self._apply_command(grant.request_id, command)
            except (DomainError, ValidationError) as error:
                self.session.rollback()
                grant = self._locked_grant(grant_id, device_id)
                return self._record_conflict(grant, command, str(error), results)

            record = OfflineCommand(
                warehouse_id=self.user.warehouse_id,
                grant_id=grant.id,
                client_command_id=command.client_command_id,
                sequence=command.sequence,
                command_type=command.command_type,
                payload=command.payload,
                status=OfflineCommandStatus.APPLIED,
                result={"request": response.model_dump(mode="json")},
            )
            grant.request_version = response.version
            self.session.add(record)
            self.session.commit()
            results.append(self._command_response(record))

        current_grant = self._locked_grant(grant_id, device_id)
        return OfflineSyncResponse(
            grant_id=current_grant.id,
            request_version=current_grant.request_version,
            commands=results,
        )

    def _apply_command(self, request_id: UUID, command: OfflineCommandInput):
        request_service = RequestService(self.session, self.user)
        if command.command_type == "record_pick":
            payload = RecordPickRequest.model_validate(command.payload)
            return request_service.record_pick(
                request_id,
                allocation_id=payload.allocation_id,
                quantity=payload.quantity,
                scanned_location_code=payload.scanned_location_code,
                scanned_sku=payload.scanned_sku,
                shortage_reason=payload.shortage_reason,
                commit=False,
            )
        return request_service.handoff(request_id, commit=False)

    def _locked_grant(self, grant_id: UUID, device_id: str) -> OfflineGrant:
        DeviceService(self.session, self.user).assert_active(device_id)
        grant = self.session.scalar(
            select(OfflineGrant)
            .where(
                OfflineGrant.id == grant_id,
                OfflineGrant.warehouse_id == self.user.warehouse_id,
                OfflineGrant.user_id == self.user.id,
                OfflineGrant.device_id == device_id,
                OfflineGrant.expires_at > utc_now(),
                OfflineGrant.revoked_at.is_(None),
            )
            .with_for_update()
        )
        if grant is None:
            raise NotFoundError("Active offline grant not found")
        return grant

    def _record_conflict(
        self,
        grant: OfflineGrant,
        command: OfflineCommandInput,
        message: str,
        previous_results: list[OfflineCommandResult],
    ) -> OfflineSyncResponse:
        record = OfflineCommand(
            warehouse_id=self.user.warehouse_id,
            grant_id=grant.id,
            client_command_id=command.client_command_id,
            sequence=command.sequence,
            command_type=command.command_type,
            payload=command.payload,
            status=OfflineCommandStatus.CONFLICT,
            result={"detail": message},
        )
        self.session.add(record)
        self.session.commit()
        return OfflineSyncResponse(
            grant_id=grant.id,
            request_version=grant.request_version,
            commands=[*previous_results, self._command_response(record)],
        )

    def _assert_manager(self) -> None:
        if not self.user.roles.intersection(
            {Role.INVENTORY_MANAGER, Role.SYSTEM_ADMINISTRATOR}
        ):
            raise PermissionDeniedError("Offline conflicts require manager access")

    @staticmethod
    def _conflict_response(
        command: OfflineCommand,
        grant: OfflineGrant,
        request_number: str,
        actor_name: str,
    ) -> OfflineConflictResponse:
        return OfflineConflictResponse(
            id=command.id,
            grant_id=grant.id,
            request_id=grant.request_id,
            request_number=request_number,
            actor_user_id=grant.user_id,
            actor_name=actor_name,
            device_id=grant.device_id,
            sequence=command.sequence,
            command_type=command.command_type,
            payload=command.payload,
            status=command.status,
            result=command.result,
            created_at=command.created_at.isoformat(),
        )

    @staticmethod
    def _command_response(command: OfflineCommand) -> OfflineCommandResult:
        return OfflineCommandResult(
            client_command_id=command.client_command_id,
            sequence=command.sequence,
            status=command.status,
            result=command.result,
        )
