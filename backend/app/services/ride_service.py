"""Ride publishing, discovery and serialisation (§7, §8).

Privacy model (see `documentation/02-database-design.md`):

* `pickup_area` / `destination_area` are coarse labels — always public.
* `pickup_latitude/longitude` are the exact meeting spot — returned only to the
  driver, the matched passenger, and administrators.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.enums import (
    ContributionType,
    FuelPreference,
    RideDirection,
    RideRequestStatus,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
    VehicleType,
)
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.ride import (
    ContributionOut,
    DriverSummary,
    GeoPoint,
    RideCreateIn,
    RideDetailOut,
    RideListOut,
    RideOut,
    RideUpdateIn,
    VehicleSummary,
)
from app.services.notification_service import create_notification_from_template
from app.utils.pagination import decode_cursor, encode_cursor

PUBLIC_RIDE_STATUSES = (RideStatus.OPEN,)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------- publishing
def create_ride(db: Session, driver: User, payload: RideCreateIn) -> Ride:
    from app.services.vehicle_service import resolve_publish_vehicle

    vehicle = resolve_publish_vehicle(db, driver, payload.vehicle_id)

    if payload.available_seats > settings.MAX_CONFIRMED_PASSENGERS:
        raise ValidationAppError(
            f"A published journey can currently offer {settings.MAX_CONFIRMED_PASSENGERS} seat(s).",
            details={"available_seats": "too many"},
        )

    departure = _aware(payload.departure_at) or utcnow()
    _guard_driver_schedule(db, driver, departure)

    to_university = payload.direction is RideDirection.HOME_TO_UNIVERSITY
    pickup_area = payload.pickup_area if to_university else settings.UNIVERSITY_AREA_LABEL
    pickup_point = payload.pickup_point if to_university else GeoPoint(
        latitude=settings.SSUET_LATITUDE, longitude=settings.SSUET_LONGITUDE
    )
    destination_area = payload.destination_area if not to_university else settings.UNIVERSITY_AREA_LABEL
    destination_point = payload.destination_point if not to_university else GeoPoint(
        latitude=settings.SSUET_LATITUDE, longitude=settings.SSUET_LONGITUDE
    )

    ride = Ride(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        vehicle_type=vehicle.vehicle_type,
        direction=payload.direction,
        pickup_area=pickup_area.strip(),
        pickup_latitude=pickup_point.latitude,
        pickup_longitude=pickup_point.longitude,
        destination_area=destination_area.strip(),
        destination_latitude=destination_point.latitude,
        destination_longitude=destination_point.longitude,
        departure_date=departure.replace(hour=0, minute=0, second=0, microsecond=0),
        departure_at=departure,
        available_seats=payload.available_seats,
        seats_remaining=payload.available_seats,
        fuel_preference=payload.fuel_preference,
        contribution_type=payload.contribution_type,
        contribution_amount=payload.contribution_amount,
        contribution_note=payload.contribution_note,
        note=payload.note,
        status=RideStatus.OPEN,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


def _guard_driver_schedule(db: Session, driver: User, departure: datetime) -> None:
    window = timedelta(minutes=settings.MIN_MINUTES_BETWEEN_DRIVER_RIDES)
    clash = db.scalar(
        select(Ride.id).where(
            Ride.driver_id == driver.id,
            Ride.deleted_at.is_(None),
            Ride.status.in_([RideStatus.OPEN, RideStatus.MATCHED, RideStatus.IN_PROGRESS]),
            Ride.departure_at > departure - window,
            Ride.departure_at < departure + window,
        )
    )
    if clash is not None:
        raise ConflictError(
            f"You already have a journey departing within {settings.MIN_MINUTES_BETWEEN_DRIVER_RIDES} "
            "minutes of this time."
        )


def update_ride(db: Session, ride: Ride, actor: User, payload: RideUpdateIn) -> Ride:
    if ride.driver_id != actor.id:
        raise ForbiddenError("Only the driver can edit this journey.")
    if ride.status is not RideStatus.OPEN:
        raise ConflictError("This journey can only be edited while it is still open.")

    data = payload.model_dump(exclude_unset=True)

    if "departure_at" in data and data["departure_at"] is not None:
        departure = _aware(data["departure_at"]) or utcnow()
        if departure < utcnow() + timedelta(minutes=5):
            raise ValidationAppError("Departure must be at least 5 minutes in the future.")
        _guard_driver_schedule(db, actor, departure)
        data["departure_at"] = departure
        data["departure_date"] = departure.replace(hour=0, minute=0, second=0, microsecond=0)

    if "vehicle_id" in data and data["vehicle_id"] is not None:
        from app.services.vehicle_service import resolve_publish_vehicle

        vehicle = resolve_publish_vehicle(db, actor, data.pop("vehicle_id"))
        ride.vehicle_id = vehicle.id
        ride.vehicle_type = vehicle.vehicle_type

    for side in ("pickup", "destination"):
        point = data.pop(f"{side}_point", None)
        if point is not None:
            setattr(ride, f"{side}_latitude", point["latitude"] if isinstance(point, dict) else point.latitude)
            setattr(ride, f"{side}_longitude", point["longitude"] if isinstance(point, dict) else point.longitude)
        area = data.get(f"{side}_area")
        if area is not None:
            data[f"{side}_area"] = area.strip()

    fuel = data.pop("fuel_preference", None)
    contribution_type = data.pop("contribution_type", None)
    contribution_amount = data.pop("contribution_amount", "unchanged")
    contribution_note = data.pop("contribution_note", "unchanged")

    for field, value in data.items():
        setattr(ride, field, value)

    if fuel is not None:
        ride.fuel_preference = fuel
    if contribution_type is not None:
        ride.contribution_type = contribution_type
    if contribution_amount != "unchanged":
        ride.contribution_amount = contribution_amount
    if contribution_note != "unchanged":
        ride.contribution_note = contribution_note

    if ride.fuel_preference is FuelPreference.FREE:
        ride.contribution_type = ContributionType.NONE
        ride.contribution_amount = None
        ride.contribution_note = None
    elif ride.contribution_type is ContributionType.NONE:
        raise ValidationAppError("Choose how the fuel expense is shared: fixed, expected or negotiable.")
    elif ride.contribution_type is ContributionType.NEGOTIABLE:
        ride.contribution_amount = None
    elif ride.contribution_type in (ContributionType.FIXED, ContributionType.EXPECTED) and not (
        ride.contribution_amount and ride.contribution_amount > 0
    ):
        raise ValidationAppError("Enter the amount per passenger for a fixed or expected fuel share.")

    db.commit()
    db.refresh(ride)
    return ride


def cancel_ride(
    db: Session, ride: Ride, actor: User, reason: str | None, *, as_admin: bool = False
) -> Ride:
    """Driver (or admin) cancels a journey before it starts (§10)."""
    if not as_admin and ride.driver_id != actor.id:
        raise ForbiddenError("Only the driver can cancel this journey.")
    if ride.status in (RideStatus.COMPLETED, RideStatus.CANCELLED, RideStatus.EXPIRED):
        raise ConflictError("This journey can no longer be cancelled.")

    ride.status = RideStatus.CANCELLED
    ride.cancelled_at = utcnow()
    ride.cancellation_reason = reason
    ride.is_admin_cancelled = as_admin
    ride.seats_remaining = ride.available_seats

    # Notify the accepted passenger, if any.
    trip = db.scalar(
        select(Trip).where(Trip.ride_id == ride.id, Trip.status != TripStatus.CANCELLED)
    )
    if trip is not None:
        trip.status = TripStatus.CANCELLED
        trip.cancelled_at = utcnow()
        trip.cancelled_by_id = actor.id
        trip.cancellation_reason = reason
        create_notification_from_template(
            db,
            user_id=trip.passenger_id,
            template="TRIP_CANCELLED",
            commit=False,
            driver_name=actor.full_name,
            area=ride.pickup_area,
            reason=reason or "No reason given",
        )

    # Everyone still waiting is told the ride is gone.
    for pending in db.scalars(
        select(RideRequest).where(
            RideRequest.ride_id == ride.id, RideRequest.status == RideRequestStatus.PENDING
        )
    ):
        pending.status = RideRequestStatus.REJECTED
        pending.responded_at = utcnow()
        pending.response_note = "The journey was cancelled by the driver."
        create_notification_from_template(
            db,
            user_id=pending.passenger_id,
            template="RIDE_CANCELLED",
            commit=False,
            area=ride.pickup_area,
            reason=reason or "No reason given",
        )

    db.commit()
    db.refresh(ride)
    return ride


# ---------------------------------------------------------------- discovery
def _bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Cheap, index-friendly bounding box (PostGIS is overkill for one city)."""
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def list_rides(
    db: Session,
    *,
    viewer: User | None,
    direction: RideDirection | None = None,
    vehicle_type: VehicleType | None = None,
    fuel_preference: FuelPreference | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    departure_after: datetime | None = None,
    departure_before: datetime | None = None,
    area: str | None = None,
    near: GeoPoint | None = None,
    radius_km: float | None = None,
    exclude_own: bool = False,
    limit: int = 20,
    cursor: str | None = None,
) -> RideListOut:
    now = utcnow()
    stmt = (
        select(Ride)
        .options(
            joinedload(Ride.driver),
            joinedload(Ride.vehicle),
            selectinload(Ride.trips),
            selectinload(Ride.requests),
        )
        .where(
            Ride.deleted_at.is_(None),
            Ride.status == RideStatus.OPEN,
            Ride.seats_remaining > 0,
            Ride.departure_at > now,
        )
    )

    if direction is not None:
        stmt = stmt.where(Ride.direction == direction)
    if vehicle_type is not None:
        stmt = stmt.where(Ride.vehicle_type == vehicle_type)
    if fuel_preference is not None:
        stmt = stmt.where(Ride.fuel_preference == fuel_preference)
    if date_from is not None:
        stmt = stmt.where(Ride.departure_at >= _aware(date_from))
    if date_to is not None:
        stmt = stmt.where(Ride.departure_at <= _aware(date_to))
    if departure_after is not None:
        stmt = stmt.where(Ride.departure_at >= _aware(departure_after))
    if departure_before is not None:
        stmt = stmt.where(Ride.departure_at <= _aware(departure_before))
    if area:
        needle = f"%{area.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Ride.pickup_area).like(needle),
                func.lower(Ride.destination_area).like(needle),
            )
        )
    if near is not None:
        radius = radius_km or settings.DEFAULT_DISCOVERY_RADIUS_KM
        lat_min, lat_max, lng_min, lng_max = _bbox(near.latitude, near.longitude, radius)
        stmt = stmt.where(
            Ride.pickup_latitude.between(lat_min, lat_max),
            Ride.pickup_longitude.between(lng_min, lng_max),
        )
    if exclude_own and viewer is not None:
        stmt = stmt.where(Ride.driver_id != viewer.id)

    # never show rides published by members the viewer has blocked (or who blocked them)
    if viewer is not None:
        from app.models.user import UserBlock

        blocked = select(UserBlock.blocked_id).where(UserBlock.blocker_id == viewer.id)
        blocked_by = select(UserBlock.blocker_id).where(UserBlock.blocked_id == viewer.id)
        stmt = stmt.where(Ride.driver_id.notin_(blocked), Ride.driver_id.notin_(blocked_by))

    if cursor:
        cursor_ts, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Ride.departure_at > cursor_ts,
                and_(Ride.departure_at == cursor_ts, Ride.id > cursor_id),
            )
        )

    rows = list(db.scalars(stmt.order_by(Ride.departure_at.asc(), Ride.id.asc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]

    my_requests = _requests_by_ride(db, viewer, [ride.id for ride in rows])
    items = [serialize_ride(ride, viewer, my_request=my_requests.get(ride.id)) for ride in rows]
    next_cursor = (
        encode_cursor(_aware(rows[-1].departure_at) or now, rows[-1].id) if has_more and rows else None
    )
    return RideListOut(items=items, next_cursor=next_cursor, count=len(items))


def _requests_by_ride(
    db: Session, viewer: User | None, ride_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RideRequest]:
    if viewer is None or not ride_ids:
        return {}
    rows = db.scalars(
        select(RideRequest).where(
            RideRequest.passenger_id == viewer.id,
            RideRequest.ride_id.in_(ride_ids),
            RideRequest.status.in_([RideRequestStatus.PENDING, RideRequestStatus.ACCEPTED]),
        )
    )
    return {row.ride_id: row for row in rows}


def get_ride(db: Session, ride_id: uuid.UUID) -> Ride:
    ride = db.get(Ride, ride_id)
    if ride is None or ride.deleted_at is not None:
        raise NotFoundError("This journey could not be found.")
    return ride


def list_my_rides(db: Session, driver: User, status: RideStatus | None = None) -> list[Ride]:
    stmt = select(Ride).where(Ride.driver_id == driver.id, Ride.deleted_at.is_(None))
    if status is not None:
        stmt = stmt.where(Ride.status == status)
    return list(db.scalars(stmt.order_by(Ride.departure_at.desc())))


# ------------------------------------------------------------ serialisation
def _can_see_exact_location(ride: Ride, viewer: User | None) -> bool:
    """Driver, matched passenger and administrators see the exact meeting point."""
    if viewer is None:
        return False
    if viewer.role is UserRole.ADMIN or ride.driver_id == viewer.id:
        return True
    for trip in ride.trips or []:
        if trip.passenger_id == viewer.id and trip.status is not TripStatus.CANCELLED:
            return True
    return False


def serialize_ride(
    ride: Ride,
    viewer: User | None,
    *,
    my_request: RideRequest | None = None,
    detail: bool = False,
) -> RideOut | RideDetailOut:
    driver = ride.driver
    vehicle = ride.vehicle
    sees_location = _can_see_exact_location(ride, viewer)

    contribution = None
    if ride.fuel_preference is FuelPreference.SHARE_FUEL:
        contribution = ContributionOut(
            type=ride.contribution_type,
            amount=float(ride.contribution_amount) if ride.contribution_amount is not None else None,
            note=ride.contribution_note,
        )

    is_own = viewer is not None and ride.driver_id == viewer.id
    can_request = bool(
        viewer is not None
        and not is_own
        and ride.status is RideStatus.OPEN
        and ride.seats_remaining > 0
        and (_aware(ride.departure_at) or utcnow()) > utcnow()
        and (my_request is None or my_request.status not in (RideRequestStatus.PENDING, RideRequestStatus.ACCEPTED))
    )

    common = dict(
        id=ride.id,
        direction=ride.direction,
        status=ride.status,
        driver=DriverSummary(
            id=driver.id,
            full_name=driver.full_name,
            profile_photo_url=driver.photo_url,
            role=driver.role,
            department=driver.department,
            verification_status=driver.verification_status,
            rating_average=driver.rating_average,
            rating_count=driver.rating_count,
            completed_trips_count=driver.completed_trips_count,
        ),
        vehicle=(
            VehicleSummary(
                vehicle_type=vehicle.vehicle_type,
                make_and_model=vehicle.make_and_model,
                color=vehicle.color,
                is_verified=vehicle.status is VehicleStatus.VERIFIED,
            )
            if vehicle is not None
            else None
        ),
        pickup_area=ride.pickup_area,
        destination_area=ride.destination_area,
        departure_at=_aware(ride.departure_at),
        departure_date=_aware(ride.departure_date),
        available_seats=ride.available_seats,
        seats_remaining=ride.seats_remaining,
        fuel_preference=ride.fuel_preference,
        contribution=contribution,
        note=ride.note,
        created_at=_aware(ride.created_at),
        is_own_ride=is_own,
        can_request=can_request,
        my_request_status=my_request.status if my_request else None,
        my_trip_id=(
            next(
                (
                    trip.id
                    for trip in (ride.trips or [])
                    if viewer is not None
                    and trip.passenger_id == viewer.id
                    and trip.status is not TripStatus.CANCELLED
                ),
                None,
            )
        ),
        pickup_point=(
            GeoPoint(latitude=ride.pickup_latitude, longitude=ride.pickup_longitude)
            if sees_location
            else None
        ),
    )

    if not detail:
        return RideOut(**common)

    pending_count = (
        len([r for r in (ride.requests or []) if r.status is RideRequestStatus.PENDING])
        if is_own
        else 0
    )

    return RideDetailOut(
        **common,
        destination_point=(
            GeoPoint(latitude=ride.destination_latitude, longitude=ride.destination_longitude)
            if sees_location
            else None
        ),
        driver_note=ride.note,
        pending_requests_count=pending_count,
        driver_phone=driver.phone if is_own or sees_location else None,
    )
