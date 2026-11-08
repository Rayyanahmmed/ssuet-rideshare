"""Ride requests and the **atomic** seat reservation (§9).

The business rule of the whole product — *one published ride carries exactly one
confirmed passenger* — is protected by three independent layers:

1. `SELECT ... FOR UPDATE` on the ride row, so two accepting requests serialise.
2. In-transaction validation of `ride.status` / `seats_remaining`.
3. A partial unique index in PostgreSQL:
   `uq_trips_one_active_per_ride ON trips (ride_id) WHERE status <> 'CANCELLED'`.

If layers 1–2 are ever bypassed (a second worker, a race, a bug), layer 3 raises
`IntegrityError`, which is translated to `409 RIDE_NOT_AVAILABLE` — never a
double-booked journey.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    SeatUnavailableError,
    ValidationAppError,
)
from app.models.chat import Conversation
from app.models.enums import RideRequestStatus, RideStatus, TripStatus
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import User, UserBlock
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.requests")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _blocked_between(db: Session, first: uuid.UUID, second: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(UserBlock.id).where(
                ((UserBlock.blocker_id == first) & (UserBlock.blocked_id == second))
                | ((UserBlock.blocker_id == second) & (UserBlock.blocked_id == first))
            )
        )
        is not None
    )


# --------------------------------------------------------------- passenger
def create_request(
    db: Session, passenger: User, ride_id: uuid.UUID, message: str | None
) -> RideRequest:
    ride = db.get(Ride, ride_id)
    if ride is None or ride.deleted_at is not None:
        raise NotFoundError("This journey could not be found.")

    if ride.driver_id == passenger.id:
        raise ValidationAppError("You cannot request a seat on your own journey.")
    if ride.status is not RideStatus.OPEN or ride.seats_remaining < 1:
        raise SeatUnavailableError("This journey is no longer available.")
    if (_aware(ride.departure_at) or utcnow()) <= utcnow():
        raise ConflictError("This journey has already departed.")
    if _blocked_between(db, passenger.id, ride.driver_id):
        raise ForbiddenError("You cannot request this journey.", details={"reason_code": "BLOCKED"})

    existing = db.scalar(
        select(RideRequest).where(
            RideRequest.ride_id == ride.id,
            RideRequest.passenger_id == passenger.id,
            RideRequest.status.in_([RideRequestStatus.PENDING, RideRequestStatus.ACCEPTED]),
        )
    )
    if existing is not None:
        raise ConflictError(
            "You already have an active request for this journey.",
            details={"request_id": str(existing.id), "status": existing.status.value},
        )

    request = RideRequest(ride_id=ride.id, passenger_id=passenger.id, message=message)
    db.add(request)
    try:
        db.flush()
        create_notification_from_template(
            db,
            user_id=ride.driver_id,
            template="RIDE_REQUEST_RECEIVED",
            commit=False,
            passenger_name=passenger.full_name,
            area=ride.pickup_area,
            data={"screen": "my-rides", "tab": "published", "request_id": str(request.id)},
        )
        db.commit()
    except IntegrityError:
        # the partial unique index stopped a duplicate pending request
        db.rollback()
        raise ConflictError("You already have an active request for this journey.") from None

    db.refresh(request)
    return request


def cancel_request(db: Session, request: RideRequest, passenger: User) -> RideRequest:
    if request.passenger_id != passenger.id:
        raise ForbiddenError("This request belongs to another member.")
    if request.status is not RideRequestStatus.PENDING:
        raise ConflictError("Only a pending request can be cancelled.")
    request.status = RideRequestStatus.CANCELLED
    request.responded_at = utcnow()
    db.commit()
    db.refresh(request)
    return request


def list_my_requests(db: Session, passenger: User, status: RideRequestStatus | None = None):
    stmt = (
        select(RideRequest)
        .options(
            # one strategy per path: joined loads for to-one, selectin for collections
            joinedload(RideRequest.ride).options(
                joinedload(Ride.driver),
                joinedload(Ride.vehicle),
                selectinload(Ride.trips),
                selectinload(Ride.requests),
            ),
        )
        .where(RideRequest.passenger_id == passenger.id)
        .order_by(RideRequest.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(RideRequest.status == status)
    return list(db.scalars(stmt))


# ------------------------------------------------------------------ driver
def list_requests_for_ride(db: Session, ride: Ride, driver: User) -> list[RideRequest]:
    if ride.driver_id != driver.id and driver.role.value != "ADMIN":
        raise ForbiddenError("Only the driver can see the requests for this journey.")
    return list(
        db.scalars(
            select(RideRequest)
            .options(joinedload(RideRequest.passenger))
            .where(RideRequest.ride_id == ride.id)
            .order_by(RideRequest.created_at.asc())
        )
    )


def list_requests_for_driver(db: Session, driver: User) -> list[RideRequest]:
    return list(
        db.scalars(
            select(RideRequest)
            .options(
                joinedload(RideRequest.passenger),
                joinedload(RideRequest.ride).options(
                    selectinload(Ride.trips), selectinload(Ride.requests)
                ),
            )
            .join(Ride, Ride.id == RideRequest.ride_id)
            .where(Ride.driver_id == driver.id)
            .order_by(RideRequest.created_at.desc())
        )
    )


def reject_request(
    db: Session, request_id: uuid.UUID, driver: User, note: str | None = None
) -> RideRequest:
    request = db.get(RideRequest, request_id)
    if request is None:
        raise NotFoundError("This request could not be found.")

    ride = db.get(Ride, request.ride_id)
    if ride is None or ride.driver_id != driver.id:
        raise ForbiddenError("Only the driver can respond to this request.")
    if request.status is not RideRequestStatus.PENDING:
        raise ConflictError("This request has already been answered.")

    request.status = RideRequestStatus.REJECTED
    request.responded_at = utcnow()
    request.response_note = note
    create_notification_from_template(
        db,
        user_id=request.passenger_id,
        template="RIDE_REQUEST_REJECTED",
        commit=False,
        driver_name=driver.full_name,
        area=ride.pickup_area,
        data={"screen": "my-rides", "tab": "requested"},
    )
    db.commit()
    db.refresh(request)
    return request


def accept_request(db: Session, request_id: uuid.UUID, driver: User) -> Trip:
    """Accept a request and reserve the single seat — atomically."""
    request = db.get(RideRequest, request_id)
    if request is None:
        raise NotFoundError("This request could not be found.")

    # ---- lock the ride so concurrent accepts queue up (PostgreSQL row lock) ----
    ride = db.scalar(select(Ride).where(Ride.id == request.ride_id).with_for_update())
    if ride is None:
        raise NotFoundError("This journey could not be found.")
    if ride.driver_id != driver.id:
        raise ForbiddenError("Only the driver can accept requests for this journey.")

    db.refresh(request)

    # Ordering matters for the passenger's experience: if the seat went to someone
    # else, that is the fact worth surfacing — not "your request was auto-declined".
    ride_unavailable = ride.status is not RideStatus.OPEN or ride.seats_remaining < 1
    if request.status is not RideRequestStatus.PENDING:
        if ride_unavailable:
            raise SeatUnavailableError("This journey has just been taken by another passenger.")
        raise ConflictError("This request has already been answered.")
    if ride_unavailable:
        raise SeatUnavailableError("This journey already has a confirmed passenger.")

    # ---- create the trip first: the partial unique index is the final guard ----
    trip = Trip(
        ride_id=ride.id,
        request_id=request.id,
        driver_id=driver.id,
        passenger_id=request.passenger_id,
        status=TripStatus.CONFIRMED,
        meeting_point=ride.pickup_area,
        meeting_latitude=ride.pickup_latitude,
        meeting_longitude=ride.pickup_longitude,
    )
    db.add(trip)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.warning("Seat reservation race lost for ride %s", ride.id)
        raise SeatUnavailableError("This journey has just been taken by another passenger.") from None

    # ---- reserve the seat ----
    ride.status = RideStatus.MATCHED
    ride.seats_remaining = max(0, ride.seats_remaining - 1)
    ride.matched_at = utcnow()

    request.status = RideRequestStatus.ACCEPTED
    request.responded_at = utcnow()

    # ---- everyone else waiting is politely declined ----
    for other in db.scalars(
        select(RideRequest).where(
            RideRequest.ride_id == ride.id,
            RideRequest.id != request.id,
            RideRequest.status == RideRequestStatus.PENDING,
        )
    ):
        other.status = RideRequestStatus.REJECTED
        other.responded_at = utcnow()
        other.response_note = "Another passenger was accepted for this journey."
        create_notification_from_template(
            db,
            user_id=other.passenger_id,
            template="RIDE_REQUEST_REJECTED",
            commit=False,
            driver_name=driver.full_name,
            area=ride.pickup_area,
        )

    # ---- private trip chat (§11) ----
    conversation = Conversation(
        trip_id=trip.id,
        last_message_at=utcnow(),
        last_message_preview="Trip chat opened — coordinate your meeting point here.",
    )
    db.add(conversation)

    # ---- notify both sides ----
    create_notification_from_template(
        db,
        user_id=request.passenger_id,
        template="RIDE_REQUEST_ACCEPTED",
        commit=False,
        driver_name=driver.full_name,
        area=ride.pickup_area,
        data={"screen": "trip", "trip_id": str(trip.id)},
    )
    create_notification_from_template(
        db,
        user_id=driver.id,
        template="RIDE_REQUEST_ACCEPTED",
        commit=False,
        driver_name=request.passenger.full_name if request.passenger else "Your passenger",
        area=ride.pickup_area,
        data={"screen": "trip", "trip_id": str(trip.id)},
    )

    db.commit()
    db.refresh(trip)
    return trip
