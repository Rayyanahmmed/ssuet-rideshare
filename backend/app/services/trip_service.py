"""Trip lifecycle — start, complete, cancel, no-show (§10, §11).

A `Trip` is created when a driver accepts a request (see
`request_service.accept_request`). Phase 4 is everything that can happen to it
afterwards:

```
CONFIRMED ──start──▶ IN_PROGRESS ──both sides confirm──▶ COMPLETED
    │                     │
    ├──cancel─────────────┤ (passenger may only cancel before start)
    │                     └──cancel (driver)──▶ CANCELLED
    └──no-show (driver)──▶ NO_SHOW
```

Design rules encoded here:

* **Only the driver can start a trip.** The passenger cannot claim a journey is
  happening; the person holding the keys decides.
* **Completion needs both sides.** Each participant sets their own confirmation
  flag; the trip (and its ride) only become `COMPLETED` when both are set — so a
  driver cannot farm completed-trip counts, and a passenger cannot silently
  finish a journey that never happened.
* **Cancelling as a passenger frees the seat.** The ride returns to `OPEN` with
  its seat restored, so someone else can still travel with the same driver.
  Cancelling as a driver kills the ride — nobody is driving.
* **No-show is the driver's tool** for a passenger who never turned up. It is
  recorded separately from a cancellation so the admin dashboard (Phase 6) can
  tell the two apart.
* Every state change respects `TRIP_STATUS_TRANSITIONS` / `RIDE_STATUS_TRANSITIONS`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.chat import Conversation
from app.models.payment import TripPayment
from app.models.enums import (
    RIDE_STATUS_TRANSITIONS,
    TRIP_STATUS_TRANSITIONS,
    RideRequestStatus,
    RideStatus,
    TripStatus,
    PaymentStatus,
    UserRole,
)
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import User
from app.schemas.ride import DriverSummary, GeoPoint, RequesterSummary, VehicleSummary
from app.schemas.trip import CounterpartOut, TripListOut, TripOut
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.trips")

#: A journey may be started up to six hours early (traffic, exams, early labs)…
START_EARLY_WINDOW = timedelta(hours=6)
#: …and up to twelve hours late, after which maintenance expires it.
START_LATE_WINDOW = timedelta(hours=12)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _transition(entity: object, current: object, target: object, table: dict) -> None:
    """Central guard so no endpoint can invent an illegal state change."""

    if target not in table.get(current, set()):  # type: ignore[arg-type]
        raise ConflictError(f"This trip cannot move from {current} to {target}.")


# --------------------------------------------------------------------- reads
def get_trip_or_404(db: Session, trip_id: uuid.UUID) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    return trip


def load_trip_for(db: Session, trip_id: uuid.UUID, viewer: User) -> Trip:
    """Fetch a trip and assert the viewer is one of its two participants."""

    trip = get_trip_or_404(db, trip_id)
    if viewer.role is not UserRole.ADMIN and not trip.involves(viewer.id):
        raise ForbiddenError("You can only open trips you are part of.")
    return trip


def list_trips(
    db: Session,
    viewer: User,
    *,
    role: str | None = None,
    status: TripStatus | None = None,
    upcoming: bool | None = None,
    limit: int = 50,
) -> TripListOut:
    """Trips the viewer is part of, as driver and/or passenger."""

    query = select(Trip).where(or_(Trip.driver_id == viewer.id, Trip.passenger_id == viewer.id))

    if role == "DRIVER":
        query = query.where(Trip.driver_id == viewer.id)
    elif role == "PASSENGER":
        query = query.where(Trip.passenger_id == viewer.id)
    elif role is not None:
        raise ValidationAppError("role must be DRIVER or PASSENGER.")

    if status is not None:
        query = query.where(Trip.status == status)
    if upcoming is True:
        query = query.where(Trip.status.in_([TripStatus.CONFIRMED, TripStatus.IN_PROGRESS]))
    elif upcoming is False:
        query = query.where(
            Trip.status.in_([TripStatus.COMPLETED, TripStatus.CANCELLED, TripStatus.NO_SHOW])
        )

    trips = list(db.scalars(query.order_by(Trip.created_at.desc()).limit(limit)).all())
    # Order by departure time: upcoming journeys soonest-first, history newest-first.
    trips.sort(
        key=lambda trip: _aware(trip.ride.departure_at) or _aware(trip.created_at) or utcnow(),
        reverse=not upcoming,
    )
    return TripListOut(items=[serialize_trip(db, trip, viewer) for trip in trips], count=len(trips))


# --------------------------------------------------------------- serialisation
def _driver_summary(user: User) -> DriverSummary:
    return DriverSummary(
        id=user.id,
        full_name=user.full_name,
        profile_photo_url=user.photo_url,
        role=user.role,
        department=user.department,
        verification_status=user.verification_status,
        rating_average=user.rating_average,
        rating_count=user.rating_count,
        completed_trips_count=user.completed_trips_count,
    )


def _requester_summary(user: User) -> RequesterSummary:
    return RequesterSummary(
        id=user.id,
        full_name=user.full_name,
        profile_photo_url=user.photo_url,
        department=user.department,
        role=user.role,
        verification_status=user.verification_status,
        rating_average=user.rating_average,
        rating_count=user.rating_count,
        completed_trips_count=user.completed_trips_count,
    )


def serialize_trip(db: Session, trip: Trip, viewer: User) -> TripOut:
    """Trip payload, including the actions *this* viewer may take next.

    Contact details and the exact meeting point are included because a trip only
    exists after a match — that is exactly the boundary §8 allows.
    """

    ride = trip.ride
    conversation = db.scalar(select(Conversation).where(Conversation.trip_id == trip.id))
    is_driver = viewer.id == trip.driver_id
    is_passenger = viewer.id == trip.passenger_id
    now = utcnow()
    departure = _aware(ride.departure_at) if ride is not None else None

    viewer_reviewed = (
        trip.passenger_reviewed_driver if is_passenger else trip.driver_reviewed_passenger
    )
    counterpart = trip.passenger if is_driver else trip.driver
    my_confirmed = trip.driver_confirmed_complete if is_driver else trip.passenger_confirmed_complete
    other_confirmed = (
        trip.passenger_confirmed_complete if is_driver else trip.driver_confirmed_complete
    )

    can_start = bool(
        is_driver
        and trip.status is TripStatus.CONFIRMED
        and departure is not None
        and departure - START_EARLY_WINDOW <= now <= departure + START_LATE_WINDOW
    )
    can_complete = bool(
        (is_driver or is_passenger)
        and not my_confirmed
        and trip.status is TripStatus.IN_PROGRESS
    ) or bool(is_driver and trip.status is TripStatus.NO_SHOW and ride is not None and ride.status is not RideStatus.COMPLETED)
    can_cancel = bool(
        trip.status is TripStatus.CONFIRMED
        or (is_driver and trip.status is TripStatus.IN_PROGRESS)
    )
    can_mark_no_show = bool(
        is_driver
        and trip.status in (TripStatus.CONFIRMED, TripStatus.IN_PROGRESS)
        and departure is not None
        and now >= departure - timedelta(minutes=30)
    )

    payment = db.scalar(select(TripPayment).where(TripPayment.trip_id == trip.id))
    payment_status = payment.status if payment is not None else None
    payment_settled = payment_status in (PaymentStatus.VERIFIED, PaymentStatus.NON_PAYMENT_REPORTED)
    # Cash payment is recorded by the driver once the trip is completed and not yet settled.
    can_settle_payment = bool(is_driver and trip.status is TripStatus.COMPLETED and not payment_settled)
    invoice_number = (
        payment.invoice_number if payment is not None and payment_status is PaymentStatus.VERIFIED else None
    )

    return TripOut(
        id=trip.id,
        ride_id=trip.ride_id,
        status=trip.status,
        direction=ride.direction if ride is not None else None,
        meeting_point=trip.meeting_point,
        meeting_location=(
            GeoPoint(latitude=trip.meeting_latitude, longitude=trip.meeting_longitude)
            if trip.meeting_latitude is not None and trip.meeting_longitude is not None
            else None
        ),
        departure_at=departure,
        pickup_area=ride.pickup_area if ride is not None else None,
        destination_area=ride.destination_area if ride is not None else None,
        vehicle=(
            VehicleSummary(
                vehicle_type=ride.vehicle.vehicle_type,
                make_and_model=ride.vehicle.make_and_model,
                color=ride.vehicle.color,
                is_verified=str(ride.vehicle.status) == "VERIFIED",
            )
            if ride is not None and ride.vehicle is not None
            else None
        ),
        fuel_preference=ride.fuel_preference if ride is not None else None,
        driver=_driver_summary(trip.driver),
        passenger=_requester_summary(trip.passenger),
        counterpart=CounterpartOut(
            id=counterpart.id,
            full_name=counterpart.full_name,
            profile_photo_url=counterpart.photo_url,
            department=counterpart.department,
            phone=counterpart.phone,
        ),
        driver_phone=trip.driver.phone,
        passenger_phone=trip.passenger.phone,
        conversation_id=conversation.id if conversation is not None else None,
        started_at=_aware(trip.started_at),
        completed_at=_aware(trip.completed_at),
        cancelled_at=_aware(trip.cancelled_at),
        cancelled_by_id=trip.cancelled_by_id,
        cancellation_reason=trip.cancellation_reason,
        driver_confirmed_complete=trip.driver_confirmed_complete,
        passenger_confirmed_complete=trip.passenger_confirmed_complete,
        awaiting_my_confirmation=bool(
            trip.status is TripStatus.IN_PROGRESS and not my_confirmed and other_confirmed
        ),
        can_review=str(trip.status) == "COMPLETED" and not viewer_reviewed,
        viewer_reviewed=viewer_reviewed,
        my_role="DRIVER" if is_driver else "PASSENGER",
        can_start=can_start,
        can_complete=can_complete,
        can_cancel=can_cancel,
        can_mark_no_show=can_mark_no_show,
        payment_status=payment_status.value if payment_status is not None else None,
        can_confirm_payment=can_settle_payment,
        can_report_non_payment=can_settle_payment,
        invoice_number=invoice_number,
        created_at=_aware(trip.created_at),
    )


# ------------------------------------------------------------------ lifecycle
def start_trip(db: Session, trip_id: uuid.UUID, driver: User) -> Trip:
    """Driver starts the journey (CONFIRMED → IN_PROGRESS)."""

    trip = get_trip_or_404(db, trip_id)
    if trip.driver_id != driver.id:
        raise ForbiddenError("Only the driver can start this trip.")
    if trip.status is TripStatus.IN_PROGRESS:
        raise ConflictError("This trip has already started.")
    if trip.status is not TripStatus.CONFIRMED:
        raise ConflictError("This trip can no longer be started.")
    _transition(trip, trip.status, TripStatus.IN_PROGRESS, TRIP_STATUS_TRANSITIONS)

    ride = trip.ride
    if ride is None:  # pragma: no cover - FK guarantees a ride
        raise NotFoundError("This journey could not be found.")
    departure = _aware(ride.departure_at) or utcnow()
    now = utcnow()
    if now < departure - START_EARLY_WINDOW:
        raise ConflictError(
            "This journey cannot be started yet — you can start it up to "
            f"{int(START_EARLY_WINDOW.total_seconds() // 3600)} hours before departure."
        )

    trip.status = TripStatus.IN_PROGRESS
    trip.started_at = now
    if trip.meeting_point is None:
        trip.meeting_point = ride.pickup_area

    if RideStatus.IN_PROGRESS in RIDE_STATUS_TRANSITIONS.get(ride.status, set()):
        ride.status = RideStatus.IN_PROGRESS
    ride.started_at = now

    create_notification_from_template(
        db,
        user_id=trip.passenger_id,
        template="TRIP_STARTED",
        commit=False,
        driver_name=driver.full_name,
        area=ride.pickup_area,
        data={"screen": "trip", "trip_id": str(trip.id)},
    )
    _commit(db, trip)
    return trip


def complete_trip(db: Session, trip_id: uuid.UUID, actor: User, note: str | None = None) -> Trip:
    """One side confirms the journey happened; both confirmations finish it."""

    trip = load_trip_for(db, trip_id, actor)
    ride = trip.ride
    if ride is None:  # pragma: no cover
        raise NotFoundError("This journey could not be found.")

    is_driver = actor.id == trip.driver_id

    if trip.status is TripStatus.NO_SHOW:
        # The passenger never turned up; the driver still travelled. Finishing the
        # ride is all that is left, and only the driver can do it.
        if not is_driver:
            raise ConflictError("This trip was marked as a no-show and cannot be completed.")
        if ride.status is RideStatus.COMPLETED:
            raise ConflictError("This trip has already been completed.")
        ride.status = RideStatus.COMPLETED
        ride.completed_at = utcnow()
        trip.completed_at = trip.completed_at or utcnow()
        _commit(db, trip)
        return trip

    if trip.status is TripStatus.COMPLETED:
        raise ConflictError("This trip has already been completed.")
    if trip.status is not TripStatus.IN_PROGRESS:
        raise ConflictError("Only a journey in progress can be completed.")
    if trip.status is TripStatus.CANCELLED:  # pragma: no cover - defensive
        raise ConflictError("This trip was cancelled.")

    if is_driver:
        if trip.driver_confirmed_complete:
            raise ConflictError("You have already confirmed this trip.")
        trip.driver_confirmed_complete = True
    else:
        if trip.passenger_confirmed_complete:
            raise ConflictError("You have already confirmed this trip.")
        trip.passenger_confirmed_complete = True

    both_confirmed = trip.driver_confirmed_complete and trip.passenger_confirmed_complete
    if both_confirmed:
        _transition(trip, trip.status, TripStatus.COMPLETED, TRIP_STATUS_TRANSITIONS)
        now = utcnow()
        trip.status = TripStatus.COMPLETED
        trip.completed_at = now
        ride.status = RideStatus.COMPLETED
        ride.completed_at = now

        # Only a real, mutually-confirmed journey strengthens a member's record.
        trip.driver.completed_trips_count += 1
        trip.passenger.completed_trips_count += 1

        for user, template_user in (
            (trip.driver_id, trip.passenger),
            (trip.passenger_id, trip.driver),
        ):
            create_notification_from_template(
                db,
                user_id=user,
                template="TRIP_COMPLETED",
                commit=False,
                area=ride.pickup_area,
                counterpart_name=template_user.full_name,
                data={"screen": "trip", "trip_id": str(trip.id)},
            )
    else:
        # Ask the other side to confirm as well.
        other_id = trip.passenger_id if is_driver else trip.driver_id
        create_notification_from_template(
            db,
            user_id=other_id,
            template="TRIP_AWAITING_CONFIRMATION",
            commit=False,
            driver_name=actor.full_name,
            area=ride.pickup_area,
            data={"screen": "trip", "trip_id": str(trip.id)},
        )

    _commit(db, trip)
    return trip


def cancel_trip(
    db: Session,
    trip_id: uuid.UUID,
    actor: User,
    reason: str | None = None,
    *,
    as_admin: bool = False,
) -> Trip:
    """Either participant cancels; the ride's fate depends on *who* cancelled."""

    trip = get_trip_or_404(db, trip_id)
    if not as_admin and not trip.involves(actor.id):
        raise ForbiddenError("You are not part of this trip.")
    if trip.status in (TripStatus.COMPLETED, TripStatus.CANCELLED, TripStatus.NO_SHOW):
        raise ConflictError("This trip can no longer be cancelled.")

    ride = trip.ride
    is_driver = actor.id == trip.driver_id

    if not is_driver and not as_admin and trip.status is TripStatus.IN_PROGRESS:
        raise ConflictError(
            "This journey has already started. Contact the driver, or use the report flow."
        )

    _transition(trip, trip.status, TripStatus.CANCELLED, TRIP_STATUS_TRANSITIONS)

    now = utcnow()
    trip.status = TripStatus.CANCELLED
    trip.cancelled_at = now
    trip.cancelled_by_id = actor.id
    trip.cancellation_reason = reason

    # The accepted request is withdrawn with the trip.
    request = db.get(RideRequest, trip.request_id)
    if request is not None and request.status is RideRequestStatus.ACCEPTED:
        request.status = RideRequestStatus.CANCELLED
        request.responded_at = now
        request.response_note = (
            "The passenger cancelled this trip."
            if not is_driver
            else "The driver cancelled this trip."
        )

    if ride is not None:
        if is_driver or as_admin:
            # Nobody is driving any more — the published journey dies with the trip.
            ride.status = RideStatus.CANCELLED
            ride.cancelled_at = now
            ride.cancellation_reason = reason or "The driver cancelled this trip."
            ride.seats_remaining = ride.available_seats
            for pending in db.scalars(
                select(RideRequest).where(
                    RideRequest.ride_id == ride.id,
                    RideRequest.status == RideRequestStatus.PENDING,
                )
            ):
                pending.status = RideRequestStatus.REJECTED
                pending.responded_at = now
                pending.response_note = "The journey was cancelled by the driver."
        elif ride.status is RideStatus.MATCHED and _aware(ride.departure_at) > now:
            # Passenger stepped out before departure: the seat is free again.
            ride.status = RideStatus.OPEN
            ride.seats_remaining = ride.available_seats
            ride.matched_at = None
            ride.started_at = None
        else:
            # Journey already departed (or is running): it cannot be re-offered.
            ride.status = RideStatus.IN_PROGRESS
            ride.seats_remaining = 0

    # The other side is always told.
    other_id = trip.passenger_id if is_driver else trip.driver_id
    create_notification_from_template(
        db,
        user_id=other_id,
        template="TRIP_CANCELLED",
        commit=False,
        driver_name=actor.full_name,
        area=ride.pickup_area if ride is not None else "your",
        reason=reason or "No reason given",
        data={"screen": "trip", "trip_id": str(trip.id)},
    )

    _commit(db, trip)
    return trip


def mark_no_show(
    db: Session, trip_id: uuid.UUID, driver: User, reason: str | None = None
) -> Trip:
    """Driver records that the passenger never turned up."""

    trip = get_trip_or_404(db, trip_id)
    if trip.driver_id != driver.id:
        raise ForbiddenError("Only the driver can mark a passenger as a no-show.")
    if trip.status not in (TripStatus.CONFIRMED, TripStatus.IN_PROGRESS):
        raise ConflictError("Only a confirmed or running trip can be marked as a no-show.")

    ride = trip.ride
    now = utcnow()
    if ride is not None:
        departure = _aware(ride.departure_at) or now
        if now < departure - timedelta(minutes=30):
            raise ConflictError("You can mark a no-show from 30 minutes before departure.")

    _transition(trip, trip.status, TripStatus.NO_SHOW, TRIP_STATUS_TRANSITIONS)
    trip.status = TripStatus.NO_SHOW
    trip.cancellation_reason = reason or "The passenger did not show up."

    if ride is not None:
        request = db.get(RideRequest, trip.request_id)
        if request is not None and request.status is RideRequestStatus.ACCEPTED:
            request.status = RideRequestStatus.CANCELLED
            request.responded_at = now
            request.response_note = "Marked as a no-show by the driver."

        if ride.status is RideStatus.IN_PROGRESS:
            # The driver keeps travelling; completion (driver-only) finishes the ride.
            ride.seats_remaining = 0
        elif _aware(ride.departure_at) and _aware(ride.departure_at) <= now:
            # Departure has passed: the driver travelled alone, the ride is over.
            ride.status = RideStatus.COMPLETED
            ride.completed_at = now
        else:
            # Still before departure: the seat becomes available again.
            ride.status = RideStatus.OPEN
            ride.seats_remaining = ride.available_seats
            ride.matched_at = None

    create_notification_from_template(
        db,
        user_id=trip.passenger_id,
        template="TRIP_NO_SHOW",
        commit=False,
        area=ride.pickup_area if ride is not None else "your",
        reason=reason or "The driver marked you as a no-show.",
        data={"screen": "trip", "trip_id": str(trip.id)},
    )

    _commit(db, trip)
    return trip


def _commit(db: Session, trip: Trip) -> None:
    db.commit()
    db.refresh(trip)
