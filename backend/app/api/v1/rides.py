"""Ride endpoints — `/api/v1/rides` (§7, §8)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, OptionalUser, VerifiedUser
from app.core.exceptions import ForbiddenError
from app.models.enums import FuelPreference, RideDirection, RideStatus, VehicleType
from app.schemas.common import MessageOut
from app.schemas.ride import (
    GeoPoint,
    RideCancelIn,
    RideCreateIn,
    RideDetailOut,
    RideListOut,
    RideOut,
    RideUpdateIn,
)
from app.services import request_service, ride_service

router = APIRouter(prefix="/rides", tags=["Rides"])


@router.post(
    "",
    response_model=RideDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a journey",
    description=(
        "Only verified members may publish. The campus end of the journey is fixed to "
        "SSUET by the backend, and a journey can offer one seat in the current model. "
        "A FREE ride cannot request money; a SHARE_FUEL ride must describe how the cost "
        "is shared (fixed, expected or negotiable). Fuel money is always settled offline."
    ),
)
def create_ride(payload: RideCreateIn, current_user: VerifiedUser, db: DbSession) -> RideDetailOut:
    ride = ride_service.create_ride(db, current_user, payload)
    db.refresh(ride)
    return ride_service.serialize_ride(ride, current_user, detail=True)  # type: ignore[return-value]


@router.get(
    "",
    response_model=RideListOut,
    summary="Explore available journeys",
    description=(
        "Discovery feed for OPEN journeys that have not departed yet. Filters: direction, "
        "vehicle type, fuel preference, date, departure window, area text and a radius "
        "around a point. Cursor pagination keeps the feed stable while new rides appear."
    ),
)
def list_rides(
    db: DbSession,
    current_user: OptionalUser,
    direction: RideDirection | None = None,
    vehicle_type: VehicleType | None = None,
    fuel_preference: FuelPreference | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    departure_after: datetime | None = None,
    departure_before: datetime | None = None,
    area: str | None = Query(default=None, max_length=80, description="Free-text area match"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, ge=1, le=100),
    exclude_own: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> RideListOut:
    near = GeoPoint(latitude=lat, longitude=lng) if lat is not None and lng is not None else None
    return ride_service.list_rides(
        db,
        viewer=current_user,
        direction=direction,
        vehicle_type=vehicle_type,
        fuel_preference=fuel_preference,
        date_from=date_from,
        date_to=date_to,
        departure_after=departure_after,
        departure_before=departure_before,
        area=area,
        near=near,
        radius_km=radius_km,
        exclude_own=exclude_own,
        limit=limit,
        cursor=cursor,
    )


@router.get("/mine", response_model=list[RideOut], summary="Rides I published")
def my_rides(
    current_user: CurrentUser,
    db: DbSession,
    ride_status: RideStatus | None = Query(default=None, alias="status"),
) -> list[RideOut]:
    rides = ride_service.list_my_rides(db, current_user, ride_status)
    return [
        ride_service.serialize_ride(
            ride,
            current_user,
            my_request=None,
        )
        for ride in rides
    ]


@router.get(
    "/{ride_id}",
    response_model=RideDetailOut,
    summary="Journey details",
    description=(
        "Exact coordinates are only returned to the driver, the matched passenger and "
        "administrators — everyone else sees the approximate area (§8)."
    ),
)
def ride_details(ride_id: uuid.UUID, current_user: OptionalUser, db: DbSession) -> RideDetailOut:
    ride = ride_service.get_ride(db, ride_id)
    my_request = None
    if current_user is not None:
        from sqlalchemy import select

        from app.models.ride import RideRequest

        my_request = db.scalar(
            select(RideRequest).where(
                RideRequest.ride_id == ride.id, RideRequest.passenger_id == current_user.id
            )
        )
    return ride_service.serialize_ride(ride, current_user, my_request=my_request, detail=True)  # type: ignore[return-value]


@router.patch("/{ride_id}", response_model=RideDetailOut, summary="Edit a journey (while OPEN)")
def update_ride(
    ride_id: uuid.UUID, payload: RideUpdateIn, current_user: CurrentUser, db: DbSession
) -> RideDetailOut:
    ride = ride_service.get_ride(db, ride_id)
    updated = ride_service.update_ride(db, ride, current_user, payload)
    return ride_service.serialize_ride(updated, current_user, detail=True)  # type: ignore[return-value]


@router.post("/{ride_id}/cancel", response_model=RideDetailOut, summary="Cancel a journey")
def cancel_ride(
    ride_id: uuid.UUID, payload: RideCancelIn, current_user: CurrentUser, db: DbSession
) -> RideDetailOut:
    ride = ride_service.get_ride(db, ride_id)
    cancelled = ride_service.cancel_ride(db, ride, current_user, payload.reason)
    return ride_service.serialize_ride(cancelled, current_user, detail=True)  # type: ignore[return-value]
