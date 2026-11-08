"""Deep health for the operations panel — `GET /admin/health` (doc 18).

`/health` answers "is the process alive" for a load balancer. This answers the
questions a person actually asks at 9 a.m.: is the database fast, is the schema at
head, how many people are waiting for me, and is the disk quietly filling up?
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.core import runtime
from app.core.config import settings
from app.models.enums import (
    ReportStatus,
    RideStatus,
    TripStatus,
    VerificationStatus,
    VehicleStatus,
)
from app.models.report import Report
from app.models.ride import Ride
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.verification import Verification
from app.services.media_service import storage_stats

logger = logging.getLogger("ssuet.rideshare.system")

_SLOW_DB_MS = 100.0


def _count(db: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return int(db.scalar(stmt) or 0)


def database_health(db: Session) -> dict[str, Any]:
    """Round-trip time to the database, plus which dialect is actually in use."""
    started = time.perf_counter()
    db.execute(text("SELECT 1"))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    # Reading the migration revision must never poison the session. On PostgreSQL a
    # failed statement aborts the whole transaction ("current transaction is aborted"),
    # so existence is checked first and the read is wrapped in a savepoint: a database
    # created by AUTO_CREATE_TABLES simply has no alembic_version table.
    revision = None
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
        if "alembic_version" in tables:
            with db.begin_nested():
                revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 - the panel is never allowed to fail
        logger.debug("Could not read the schema revision", exc_info=True)
        revision = None

    pool = None
    try:
        connection_pool = db.get_bind().pool  # type: ignore[attr-defined]
        # Structured rather than the library's status string: the console renders
        # these three numbers, and "overflow: -4" in a raw string only confused us.
        pool = {
            "size": connection_pool.size(),
            "checked_out": connection_pool.checkedout(),
            "overflow": max(connection_pool.overflow(), 0),
        }
    except Exception:  # noqa: BLE001 - NullPool (SQLite in tests) has no size()
        pool = None

    return {
        "ok": True,
        "latency_ms": latency_ms,
        "slow": latency_ms > _SLOW_DB_MS,
        "dialect": db.get_bind().dialect.name,
        "schema_revision": revision,
        "schema_head": migration_head(),
        "pool": pool,
    }


def migration_head() -> str | None:
    """The newest revision on disk, so a stale deployment is visible at a glance."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # noqa: BLE001 - panel must never fail because of this
        logger.debug("Could not resolve alembic head", exc_info=True)
        return None


def media_health(db: Session) -> dict[str, Any]:
    stats = storage_stats(db)
    root = Path(settings.MEDIA_ROOT).expanduser()
    free_bytes = None
    total_bytes = None
    try:
        usage = __import__("shutil").disk_usage(root if root.exists() else root.parent)
        free_bytes = usage.free
        total_bytes = usage.total
    except OSError:  # pragma: no cover - unreadable volume
        pass
    return {
        "root": str(root),
        "files": stats.files,
        "bytes": stats.bytes,
        "orphans": stats.orphans,
        "oldest": stats.oldest,
        "disk_free_bytes": free_bytes,
        "disk_total_bytes": total_bytes,
        "retention_days": settings.MEDIA_ORPHAN_RETENTION_DAYS,
    }


def queues(db: Session) -> dict[str, int]:
    """What the ride-share office still has to act on."""
    return {
        # Two different numbers: requests sitting in the review queue, and members
        # whose account says PENDING (a rejected member has no open request).
        "pending_verification_requests": _count(
            db, Verification, Verification.status == VerificationStatus.PENDING
        ),
        "members_awaiting_verification": _count(
            db, User, User.verification_status == VerificationStatus.PENDING
        ),
        "pending_vehicles": _count(db, Vehicle, Vehicle.status == VehicleStatus.PENDING),
        "open_reports": _count(db, Report, Report.status == ReportStatus.OPEN),
        "open_rides": _count(db, Ride, Ride.status == RideStatus.OPEN),
        "matching_rides": _count(db, Ride, Ride.status == RideStatus.MATCHED),
        "trips_in_progress": _count(db, Trip, Trip.status == TripStatus.IN_PROGRESS),
        "members": _count(db, User),
    }


def health_report(db: Session) -> dict[str, Any]:
    database = database_health(db)
    maintenance = runtime.last_maintenance()
    warnings: list[str] = []

    if database["slow"]:
        warnings.append(f"Database round-trip is {database['latency_ms']} ms")
    if database["schema_head"] and database["schema_revision"] != database["schema_head"]:
        if database["schema_revision"] is None:
            warnings.append(
                "The database has no alembic_version row (created by AUTO_CREATE_TABLES?) — "
                f"head is {database['schema_head']}; run alembic upgrade head and stamp it"
            )
        else:
            warnings.append(
                f"Schema revision {database['schema_revision']} is not head "
                f"{database['schema_head']} — run alembic upgrade head"
            )
    media = media_health(db)
    if media["disk_free_bytes"] is not None and media["disk_total_bytes"]:
        free_ratio = media["disk_free_bytes"] / media["disk_total_bytes"]
        if free_ratio < 0.10:
            warnings.append(f"Only {free_ratio:.0%} of the media volume is free")
    if settings.MAINTENANCE_INTERVAL_MINUTES > 0 and maintenance is None:
        warnings.append("In-process housekeeping has not run yet since this worker started")

    return {
        "status": "degraded" if any("Database" in w or "free" in w for w in warnings) else "ok",
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "process": runtime.process_info(),
        "database": database,
        "queues": queues(db),
        "media": media,
        "housekeeping": {
            "interval_minutes": settings.MAINTENANCE_INTERVAL_MINUTES,
            "last_run_at": maintenance.finished_at.isoformat() if maintenance else None,
            "last_result": maintenance.result if maintenance else None,
            "slow_request_threshold_ms": settings.SLOW_REQUEST_MS,
        },
        "warnings": warnings,
    }
