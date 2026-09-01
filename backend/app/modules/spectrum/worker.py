import logging
import random
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import OutboxStatus
from app.modules.spectrum.adapter import (
    PermanentSpectrumError,
    SpectrumAdapter,
    TransientSpectrumError,
)
from app.modules.spectrum.models import OutboxAttempt, OutboxEvent
from app.platform.database.base import utc_now

logger = logging.getLogger("inventory.outbox")
MAX_ATTEMPTS = 5


class OutboxProcessor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        adapter: SpectrumAdapter,
    ) -> None:
        self.session_factory = session_factory
        self.adapter = adapter

    def process_batch(self, limit: int = 20) -> int:
        event_ids = self._claim_batch(limit)
        for event_id in event_ids:
            self._process_event(event_id)
        return len(event_ids)

    def _claim_batch(self, limit: int) -> list[UUID]:
        with self.session_factory() as session:
            stale_before = utc_now() - timedelta(minutes=5)
            session.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PROCESSING,
                    OutboxEvent.updated_at < stale_before,
                )
                .values(status=OutboxStatus.PENDING, available_at=utc_now())
            )
            events = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == OutboxStatus.PENDING,
                        OutboxEvent.available_at <= utc_now(),
                    )
                    .order_by(OutboxEvent.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                ).all()
            )
            for event in events:
                event.status = OutboxStatus.PROCESSING
            session.commit()
            return [event.id for event in events]

    def _process_event(self, event_id: UUID) -> None:
        with self.session_factory() as session:
            event = session.get(OutboxEvent, event_id)
            if event is None or event.status != OutboxStatus.PROCESSING:
                return
            event.attempt_count += 1
            try:
                if event.event_type != "material_issue":
                    raise PermanentSpectrumError(
                        f"Unsupported Spectrum event type: {event.event_type}"
                    )
                result = self.adapter.post_issue(event.payload)
                event.status = OutboxStatus.SUCCEEDED
                event.processed_at = utc_now()
                event.last_error = None
                session.add(
                    OutboxAttempt(
                        warehouse_id=event.warehouse_id,
                        outbox_event_id=event.id,
                        succeeded=True,
                        response_reference=result.transaction_reference,
                    )
                )
            except PermanentSpectrumError as error:
                self._record_failure(session, event, error, retry=False)
            except (TransientSpectrumError, OSError) as error:
                self._record_failure(session, event, error, retry=True)
            except Exception as error:
                logger.exception("unexpected_spectrum_error", extra={"event_id": str(event.id)})
                self._record_failure(session, event, error, retry=True)
            session.commit()

    @staticmethod
    def _record_failure(
        session: Session,
        event: OutboxEvent,
        error: Exception,
        *,
        retry: bool,
    ) -> None:
        event.last_error = str(error)
        exhausted = event.attempt_count >= MAX_ATTEMPTS
        if retry and not exhausted:
            event.status = OutboxStatus.PENDING
            backoff_seconds = min(300, 2**event.attempt_count) + random.uniform(0, 1)
            event.available_at = utc_now() + timedelta(seconds=backoff_seconds)
        else:
            event.status = OutboxStatus.REQUIRES_REVIEW
        session.add(
            OutboxAttempt(
                warehouse_id=event.warehouse_id,
                outbox_event_id=event.id,
                succeeded=False,
                error=str(error),
            )
        )
