from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import OutboxStatus
from app.domain.errors import ConflictError
from app.modules.audit.service import record_audit
from app.modules.identity.service import AuthenticatedUser
from app.modules.spectrum.adapter import SpectrumAdapter
from app.modules.spectrum.models import OutboxAttempt, OutboxEvent, ReconciliationRun
from app.modules.spectrum.schemas import ReconciliationRunResponse
from app.platform.database.base import utc_now


class ReconciliationService:
    def __init__(
        self,
        session: Session,
        user: AuthenticatedUser,
        adapter: SpectrumAdapter,
    ) -> None:
        self.session = session
        self.user = user
        self.adapter = adapter

    def run(self) -> ReconciliationRunResponse:
        if not self.adapter.capabilities().get("reconcile", False):
            raise ConflictError("Spectrum reconciliation is unavailable")
        run = ReconciliationRun(
            warehouse_id=self.user.warehouse_id,
            initiated_by_user_id=self.user.id,
            status="running",
            started_at=utc_now(),
        )
        self.session.add(run)
        self.session.flush()
        events = self.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.warehouse_id == self.user.warehouse_id,
                OutboxEvent.event_type == "material_issue",
            )
            .order_by(OutboxEvent.created_at)
        ).all()
        differences: list[dict[str, str]] = []
        matched_count = 0
        for event in events:
            difference = self._compare_event(event)
            if difference is None:
                matched_count += 1
            else:
                differences.append(difference)
        run.status = "completed"
        run.checked_count = len(events)
        run.matched_count = matched_count
        run.difference_count = len(differences)
        run.differences = differences
        run.finished_at = utc_now()
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="spectrum.reconciled",
            entity_type="reconciliation_run",
            entity_id=run.id,
            changes={
                "checked_count": run.checked_count,
                "matched_count": run.matched_count,
                "difference_count": run.difference_count,
            },
        )
        self.session.commit()
        return self._response(run)

    def list(self, limit: int = 50) -> list[ReconciliationRunResponse]:
        runs = self.session.scalars(
            select(ReconciliationRun)
            .where(ReconciliationRun.warehouse_id == self.user.warehouse_id)
            .order_by(ReconciliationRun.started_at.desc())
            .limit(limit)
        ).all()
        return [self._response(run) for run in runs]

    def _compare_event(self, event: OutboxEvent) -> dict[str, str] | None:
        business_reference = str(event.payload.get("business_reference", event.aggregate_id))
        base = {
            "event_id": str(event.id),
            "business_reference": business_reference,
            "request_number": str(event.payload.get("request_number") or ""),
            "sku": str(event.payload.get("sku") or ""),
        }
        if event.status != OutboxStatus.SUCCEEDED:
            return {
                **base,
                "kind": "delivery_state",
                "detail": f"Local delivery state is {event.status.value}",
            }
        expected_reference = self.session.scalar(
            select(OutboxAttempt.response_reference)
            .where(
                OutboxAttempt.outbox_event_id == event.id,
                OutboxAttempt.succeeded.is_(True),
            )
            .order_by(OutboxAttempt.created_at.desc())
            .limit(1)
        )
        remote = self.adapter.find_transaction(business_reference)
        if remote is None:
            return {
                **base,
                "kind": "missing_remote",
                "detail": "Spectrum transaction was not found",
            }
        if expected_reference != remote.transaction_reference:
            return {
                **base,
                "kind": "reference_mismatch",
                "detail": (
                    f"Expected {expected_reference or 'no local reference'}; "
                    f"found {remote.transaction_reference}"
                ),
            }
        return None

    @staticmethod
    def _response(run: ReconciliationRun) -> ReconciliationRunResponse:
        return ReconciliationRunResponse(
            id=run.id,
            status=run.status,
            checked_count=run.checked_count,
            matched_count=run.matched_count,
            difference_count=run.difference_count,
            differences=run.differences,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            error=run.error,
        )