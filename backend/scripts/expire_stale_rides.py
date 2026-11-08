"""Expire stale rides and close abandoned trips (§10).

Usage
-----
    python -m scripts.expire_stale_rides                # use the configured DB
    python -m scripts.expire_stale_rides --grace 15     # expire 15 min after departure
    python -m scripts.expire_stale_rides --dry-run      # report only, no commit

Run it from cron (or a scheduled container job) when you do **not** want the API
process to run the in-process scheduler:

    */15 * * * * cd /srv/ssuet-backend && .venv/bin/python -m scripts.expire_stale_rides
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import func, select

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.enums import RideStatus, TripStatus
from app.models.ride import Ride
from app.models.trip import Trip
from app.services.maintenance_service import run_all

logger = logging.getLogger("ssuet.rideshare.maintenance")


def _summary(db) -> str:
    open_rides = db.scalar(select(func.count()).select_from(Ride).where(Ride.status == RideStatus.OPEN))
    live_trips = db.scalar(
        select(func.count()).select_from(Trip).where(Trip.status == TripStatus.IN_PROGRESS)
    )
    return f"open_rides={open_rides} in_progress_trips={live_trips}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expire stale rides and abandoned trips.")
    parser.add_argument(
        "--grace",
        type=int,
        default=settings.RIDE_AUTO_EXPIRE_GRACE_MINUTES,
        help="Minutes after departure before an unclaimed ride expires (default from settings).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would change only.")
    args = parser.parse_args(argv)

    configure_logging()
    logger.info("Maintenance run against %s", settings.DATABASE_URL.split("://")[0])

    with SessionLocal() as db:
        before = _summary(db)
        if args.dry_run:
            logger.info("Before: %s", before)
            logger.info("Dry run — nothing was changed.")
            return 0

        result = run_all(db, grace_minutes=args.grace)
        logger.info("Maintenance result: %s", result)
        logger.info("After: %s", _summary(db))

    print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
