import logging
import signal
import time

from app.config import get_settings
from app.modules.spectrum.adapter import create_spectrum_adapter
from app.modules.spectrum.worker import OutboxProcessor
from app.platform.database import SessionLocal
from app.platform.logging import configure_logging

running = True


def stop_worker(signum: int, frame: object) -> None:
    del signum, frame
    global running
    running = False


def main() -> None:
    configure_logging()
    logger = logging.getLogger("inventory.worker")
    settings = get_settings()
    processor = OutboxProcessor(
        SessionLocal, create_spectrum_adapter(settings.spectrum_adapter)
    )
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    logger.info("outbox_worker_started")
    while running:
        processed = processor.process_batch()
        if processed == 0:
            time.sleep(settings.worker_poll_seconds)
    logger.info("outbox_worker_stopped")


if __name__ == "__main__":
    main()
