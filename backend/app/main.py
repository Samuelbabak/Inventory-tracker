import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.domain.errors import DomainError
from app.modules.audit.router import router as audit_router
from app.modules.catalog.router import router as catalog_router
from app.modules.devices.router import router as devices_router
from app.modules.identity.router import router as identity_router
from app.modules.identity.admin_router import router as identity_admin_router
from app.modules.inventory.router import router as inventory_router
from app.modules.locations.router import router as locations_router
from app.modules.notifications.router import router as notifications_router
from app.modules.offline.router import router as offline_router
from app.modules.qr.router import router as qr_router
from app.modules.recipients.router import router as recipients_router
from app.modules.requests.router import router as requests_router
from app.modules.spectrum.router import router as spectrum_router
from app.platform.database.session import engine
from app.platform.logging import configure_logging

configure_logging()
logger = logging.getLogger("inventory.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    del application
    logger.info("application_started")
    yield
    engine.dispose()
    logger.info("application_stopped")


app = FastAPI(
    title="Haynes Inventory API",
    version="0.1.0",
    docs_url="/api/docs" if settings.environment != "production" else None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.include_router(audit_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(devices_router, prefix="/api/v1")
app.include_router(identity_router, prefix="/api/v1")
app.include_router(identity_admin_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(locations_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(offline_router, prefix="/api/v1")
app.include_router(qr_router, prefix="/api/v1")
app.include_router(recipients_router, prefix="/api/v1")
app.include_router(requests_router, prefix="/api/v1")
app.include_router(spectrum_router, prefix="/api/v1")


@app.middleware("http")
async def request_context(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    started_at = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        "request_completed",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return response


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message, "code": error.code},
    )


@app.get("/api/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready"}
