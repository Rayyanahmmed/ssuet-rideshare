"""Ride & request contracts (§7, §8, §9)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models.enums import (
    ContributionType,
    FuelPreference,
    RideDirection,
    RideRequestStatus,
    RideStatus,
    UserRole,
    VehicleType,
    VerificationStatus,
)
from app.schemas.common import ORMModel


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


# ------------------------------------------------------------------ create


class RideCreateIn(BaseModel):
    """Publish a journey (§7).

    Only one end of the trip is chosen by the driver — the campus end is fixed to
    SSUET by the backend, so a journey can never point at the wrong destination.
    """

    direction: RideDirection
    pickup_area: str | None = Field(
        default=None, max_length=160, description="Required for HOME_TO_UNIVERSITY"
    )
    pickup_point: GeoPoint | None = Field(default=None, description="Required for HOME_TO_UNIVERSITY")
    destination_area: str | None = Field(
        default=None, max_length=160, description="Required for UNIVERSITY_TO_HOME"
    )
    destination_point: GeoPoint | None = Field(default=None, description="Required for UNIVERSITY_TO_HOME")

    departure_at: datetime
    vehicle_id: uuid.UUID
    available_seats: int = Field(default=1, ge=1, le=8)
    fuel_preference: FuelPreference = FuelPreference.FREE
    contribution_type: ContributionType = ContributionType.NONE
    contribution_amount: float | None = Field(default=None, ge=0, le=100000)
    contribution_note: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("departure_at")
    @classmethod
    def _future_departure(cls, value: datetime) -> datetime:
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if moment < datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Departure must be at least 5 minutes in the future.")
        if moment > datetime.now(timezone.utc) + timedelta(days=30):
            raise ValueError("Journeys can only be published up to 30 days ahead.")
        return moment

    @model_validator(mode="after")
    def _location_and_fuel_rules(self) -> "RideCreateIn":
        if self.direction is RideDirection.HOME_TO_UNIVERSITY:
            if not self.pickup_area or not self.pickup_point:
                raise ValueError("A pickup area and location are required for a university-bound journey.")
        else:
            if not self.destination_area or not self.destination_point:
                raise ValueError("A destination area and location are required for a home-bound journey.")

        if self.fuel_preference is FuelPreference.FREE:
            if self.contribution_type is not ContributionType.NONE or self.contribution_amount:
                raise ValueError("A free ride cannot ask for a fuel contribution.")
        else:
            if self.contribution_type is ContributionType.NONE:
                raise ValueError("Choose how the fuel expense is shared: fixed, expected or negotiable.")
            if self.contribution_type is ContributionType.NEGOTIABLE and self.contribution_amount:
                raise ValueError("A negotiable contribution cannot have a fixed amount.")
        return self


class RideUpdateIn(BaseModel):
    """Editing is only possible while the ride is still OPEN (§10)."""

    pickup_area: str | None = Field(default=None, max_length=160)
    pickup_point: GeoPoint | None = None
    destination_area: str | None = Field(default=None, max_length=160)
    destination_point: GeoPoint | None = None
    departure_at: datetime | None = None
    vehicle_id: uuid.UUID | None = None
    fuel_preference: FuelPreference | None = None
    contribution_type: ContributionType | None = None
    contribution_amount: float | None = Field(default=None, ge=0, le=100000)
    contribution_note: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RideCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


# ------------------------------------------------------------------- read


class DriverSummary(BaseModel):
    """Public driver information shown on a ride card — no contact details."""

    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    role: UserRole
    department: str
    verification_status: VerificationStatus
    rating_average: float
    rating_count: int
    completed_trips_count: int


class VehicleSummary(BaseModel):
    vehicle_type: VehicleType
    make_and_model: str
    color: str
    is_verified: bool


class ContributionOut(BaseModel):
    type: ContributionType
    amount: float | None = None
    note: str | None = None


class RideOut(BaseModel):
    """A ride card. `pickup_point` is only filled in for authorised viewers."""

    id: uuid.UUID
    direction: RideDirection
    status: RideStatus
    driver: DriverSummary
    vehicle: VehicleSummary | None = None
    pickup_area: str
    destination_area: str
    departure_at: datetime
    departure_date: datetime
    available_seats: int
    seats_remaining: int
    fuel_preference: FuelPreference
    contribution: ContributionOut | None = None
    note: str | None = None
    created_at: datetime

    # viewer-specific context
    is_own_ride: bool = False
    can_request: bool = False
    my_request_status: RideRequestStatus | None = None
    my_trip_id: uuid.UUID | None = None  # set once I am the confirmed passenger
    pickup_point: GeoPoint | None = None  # exact location: matched/authorised only


class RideDetailOut(RideOut):
    destination_point: GeoPoint | None = None
    driver_note: str | None = None
    pending_requests_count: int = 0  # driver-only
    driver_phone: str | None = None  # driver-only


class RideListOut(BaseModel):
    items: list[RideOut]
    next_cursor: str | None = None
    count: int


# --------------------------------------------------------------- requests


class RideRequestCreateIn(BaseModel):
    message: str | None = Field(default=None, max_length=300)


class RequestOut(ORMModel):
    """Request row, serialised straight from the ORM object."""

    id: uuid.UUID
    ride_id: uuid.UUID
    status: RideRequestStatus
    message: str | None = None
    response_note: str | None = None
    responded_at: datetime | None = None
    created_at: datetime


class RequesterSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    department: str
    role: UserRole
    verification_status: VerificationStatus
    rating_average: float
    rating_count: int
    completed_trips_count: int


class RideRequestForDriverOut(RequestOut):
    """Request inbox item — the driver sees who is asking."""

    passenger: RequesterSummary
    ride_pickup_area: str
    ride_departure_at: datetime


class RideRequestForPassengerOut(RequestOut):
    """The passenger sees the ride they asked to join."""

    ride: RideOut


class MyRequestsOut(BaseModel):
    items: list[RideRequestForPassengerOut]
    count: int
