"""FastAPI application entrypoint.

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Swagger UI: http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core import runtime
from app.core.rate_limit import limiter, rate_limit_handler
from app.core.logging import configure_logging
from app.db.session import SessionLocal, engine
from app.models import Base
from app.services.admin_bootstrap import bootstrap_admin
from app.services.maintenance_service import run_all as run_maintenance
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger("ssuet.rideshare")


async def _maintenance_loop(interval_minutes: int) -> None:
    """Expire stale rides and close abandoned trips on a timer (§10).

    Runs in a worker thread so a slow query never blocks the event loop.
    """
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            def _job():
                with SessionLocal() as db:
                    return run_maintenance(
                        db,
                        grace_minutes=settings.RIDE_AUTO_EXPIRE_GRACE_MINUTES,
                        media_retention_days=settings.MEDIA_ORPHAN_RETENTION_DAYS,
                    )

            result = await asyncio.to_thread(_job)
            runtime.record_maintenance(result.as_dict())
            logger.info("Maintenance run: %s", result)
        except asyncio.CancelledError:  # pragma: no cover - shutdown
            raise
        except Exception:  # pragma: no cover - never kill the scheduler
            logger.exception("Maintenance run failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting %s v%s (%s)", settings.PROJECT_NAME, __version__, settings.ENVIRONMENT)

    if settings.AUTO_CREATE_TABLES and settings.is_sqlite:
        # Convenience only; PostgreSQL schema is owned by Alembic.
        Base.metadata.create_all(bind=engine)
        logger.warning("AUTO_CREATE_TABLES active (SQLite dev database). Use Alembic for PostgreSQL.")

    with SessionLocal() as db:
        bootstrap_admin(db)

    # Maps are no longer tied to a build-time Google key: the provider and its (encrypted)
    # credential are read from the database and rotatable from the admin console (§13).
    with SessionLocal() as db:
        from app.services import map_service

        try:
            map_config = map_service.get_config(db)
        except Exception:  # migration not applied yet — keep startup alive
            map_config = None
        if map_config is not None:
            if not map_config.enabled:
                logger.warning("Maps disabled in the admin console — the app will fall back to area lists.")
            elif map_config.needs_key and not map_config.has_key:
                logger.warning(
                    "Map provider '%s' has no API key — add one under Admin → Map API.", map_config.provider
                )
            else:
                logger.info("Maps: provider=%s style=%s key=%s", map_config.provider, map_config.style,
                            "set" if map_config.has_key else "not required")

    maintenance_task: asyncio.Task | None = None
    if settings.MAINTENANCE_INTERVAL_MINUTES > 0 and settings.ENVIRONMENT != "test":
        maintenance_task = asyncio.create_task(
            _maintenance_loop(settings.MAINTENANCE_INTERVAL_MINUTES)
        )
        logger.info(
            "Maintenance scheduler active (every %s minutes).", settings.MAINTENANCE_INTERVAL_MINUTES
        )

    yield

    if maintenance_task is not None:
        maintenance_task.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance_task
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=__version__,
    description=(
        "University ride-sharing and pooling API for Sir Syed University of "
        "Engineering & Technology (SSUET), Karachi."
    ),
    # The interactive docs map every endpoint; they stay available in development only.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
    contact={"name": "SSUET RideShare Team"},
    license_info={"name": "Proprietary"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Correlate every response with a request id, time it, and flag the slow ones.

    The id comes back in `X-Request-ID`, so a student's screenshot of an error can be
    matched against the exact log line (nginx passes the header through untouched).
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"

    path = request.url.path
    # Health probes would otherwise dominate the log at 15-second intervals.
    if not path.endswith(("/health", "/health/ready")):
        if elapsed_ms >= settings.SLOW_REQUEST_MS:
            logger.warning(
                "SLOW %s %s → %s in %.0f ms (request_id=%s)",
                request.method, path, response.status_code, elapsed_ms, request_id,
            )
        elif elapsed_ms >= 100:
            logger.info(
                "%s %s → %s in %.0f ms (request_id=%s)",
                request.method, path, response.status_code, elapsed_ms, request_id,
            )
    return response


# rate limiting (§19, §22) — per-IP limits on auth and other sensitive routes
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse(
        {
            "name": settings.PROJECT_NAME,
            "version": __version__,
            "docs": "/docs",
            "api": settings.API_V1_PREFIX,
        }
    )
