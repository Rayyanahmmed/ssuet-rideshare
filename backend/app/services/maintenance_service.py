"""Housekeeping jobs (§10) — expire stale rides, finish abandoned trips.

Nothing in here is triggered by a user. Two problems need a clock rather than a
button:

1. A journey published for 8:00 that nobody joined is still `OPEN` at 11:00.
   Left alone it pollutes Explore and blocks the driver's seat count, so after a
   grace period it becomes `EXPIRED` and its pending requests are withdrawn.
2. A trip that was started but never completed by both sides would stay
   `IN_PROGRESS` forever, skewing counts and preventing reviews. Once one side has
   confirmed and 24 hours have passed, the journey is closed on their behalf.

The functions are pure service calls that commit their own work, so they can be
invoked from the CLI (`python -m scripts.expire_stale_rides`), from the API in
Phase 6, or from the optional in-process scheduler in `app.main`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RideRequestStatus, RideStatus, TripStatus
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.maintenance")

#: How long after departure an unclaimed journey stays visible before expiring.
DEFAULT_GRACE_MINUTES = 30
#: How long an unconfirmed, still-running trip may linger before auto-completion.
AUTO_COMPLETE_HOURS = 24


@dataclass
class MaintenanceResult:
    expired_rides: int = 0
    withdrawn_requests: int = 0
    auto_completed_trips: int = 0
    abandoned_trips: int = 0
    orphaned_media: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "expired_rides": self.expired_rides,
            "withdrawn_requests": self.withdrawn_requests,
            "auto_completed_trips": self.auto_completed_trips,
            "abandoned_trips": self.abandoned_trips,
            "orphaned_media": self.orphaned_media,
        }

    def __str__(self) -> str:  # pragma: no cover - CLI output
        return ", ".join(f"{key}={value}" for key, value in self.as_dict().items())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def expire_stale_rides(
    db: Session, *, grace_minutes: int = DEFAULT_GRACE_MINUTES, now: datetime | None = None
) -> MaintenanceResult:
    """`OPEN` rides whose departure has passed → `EXPIRED`.

    `MATCHED` rides that were never started long after departure → the trip is
    cancelled (nobody started it, so nothing was "completed") and the ride expires.
    """

    moment = now or utcnow()
    grace = timedelta(minutes=grace_minutes)
    result = MaintenanceResult()

    stale = list(
        db.scalars(
            select(Ride).where(
                Ride.status.in_([RideStatus.OPEN, RideStatus.MATCHED]),
                Ride.deleted_at.is_(None),
            )
        ).all()
    )

    for ride in stale:
        departure = _aware(ride.departure_at)
        if departure is None or departure > moment - grace:
            continue

        # Nothing ever started: withdraw anything still waiting.
        for request in db.scalars(
            select(RideRequest).where(
                RideRequest.ride_id == ride.id,
                RideRequest.status == RideRequestStatus.PENDING,
            )
        ):
            request.status = RideRequestStatus.CANCELLED
            request.responded_at = moment
            request.response_note = "This journey expired because it was never started."
            result.withdrawn_requests += 1
            create_notification_from_template(
                db,
                user_id=request.passenger_id,
                template="RIDE_CANCELLED",
                commit=False,
                area=ride.pickup_area,
                reason="The journey expired without being started.",
            )

        for trip in db.scalars(
            select(Trip).where(
                Trip.ride_id == ride.id,
                Trip.status == TripStatus.CONFIRMED,
            )
        ):
            trip.status = TripStatus.CANCELLED
            trip.cancelled_at = moment
            trip.cancellation_reason = "The journey was never started and expired."
            result.abandoned_trips += 1
            create_notification_from_template(
                db,
                user_id=trip.passenger_id,
                template="TRIP_CANCELLED",
                commit=False,
                driver_name="Your driver",
                area=ride.pickup_area,
                reason="The journey was never started.",
            )

        ride.status = RideStatus.EXPIRED
        ride.seats_remaining = 0
        result.expired_rides += 1
        logger.info("Expired stale ride %s (%s)", ride.id, ride.pickup_area)

    if result.expired_rides or result.withdrawn_requests or result.abandoned_trips:
        db.commit()
    return result


def auto_complete_stale_trips(
    db: Session, *, hours: int = AUTO_COMPLETE_HOURS, now: datetime | None = None
) -> MaintenanceResult:
    """Close `IN_PROGRESS` trips that one side confirmed and the other ignored."""

    moment = now or utcnow()
    cutoff = moment - timedelta(hours=hours)
    result = MaintenanceResult()

    candidates = list(
        db.scalars(
            select(Trip).where(
                Trip.status == TripStatus.IN_PROGRESS,
                Trip.started_at.is_not(None),
                Trip.started_at <= cutoff,
                (Trip.driver_confirmed_complete.is_(True))
                | (Trip.passenger_confirmed_complete.is_(True)),
            )
        ).all()
    )

    for trip in candidates:
        trip.status = TripStatus.COMPLETED
        trip.completed_at = moment
        trip.driver_confirmed_complete = True
        trip.passenger_confirmed_complete = True
        trip.driver.completed_trips_count += 1
        trip.passenger.completed_trips_count += 1

        ride = trip.ride
        if ride is not None and ride.status is RideStatus.IN_PROGRESS:
            ride.status = RideStatus.COMPLETED
            ride.completed_at = moment

        for user_id, other in (
            (trip.driver_id, trip.passenger),
            (trip.passenger_id, trip.driver),
        ):
            create_notification_from_template(
                db,
                user_id=user_id,
                template="TRIP_COMPLETED",
                commit=False,
                area=ride.pickup_area if ride is not None else "your",
                counterpart_name=other.full_name,
                data={"screen": "trip", "trip_id": str(trip.id)},
            )
        result.auto_completed_trips += 1
        logger.info("Auto-completed stale trip %s", trip.id)

    if result.auto_completed_trips:
        db.commit()
    return result


def run_all(
    db: Session,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    media_retention_days: int | None = None,
) -> MaintenanceResult:
    """Run every clock-driven job and return the combined counts.

    Phase 10 adds the media sweep: uploads that never made it into a record are
    deleted after `MEDIA_ORPHAN_RETENTION_DAYS`, so a member who picked a photo and
    closed the app does not cost disk forever.
    """

    expired = expire_stale_rides(db, grace_minutes=grace_minutes)
    completed = auto_complete_stale_trips(db)

    # Imported here: maintenance is also imported by scripts that never touch media.
    from app.services.media_service import sweep_orphans

    swept = sweep_orphans(db, older_than_days=media_retention_days)

    return MaintenanceResult(
        expired_rides=expired.expired_rides,
        withdrawn_requests=expired.withdrawn_requests,
        auto_completed_trips=completed.auto_completed_trips,
        abandoned_trips=expired.abandoned_trips,
        orphaned_media=swept.deleted,
    )
