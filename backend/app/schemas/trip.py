"""Trip contracts (§10, §11).

A trip payload is always viewer-specific: it carries the actions *this* member may
take next (`can_start`, `can_complete`, …), so the mobile app never has to
re-implement the state machine to decide which button to show.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import FuelPreference, RideDirection, TripStatus
from app.schemas.ride import DriverSummary, GeoPoint, RequesterSummary, VehicleSummary


class CounterpartOut(BaseModel):
    """The other participant — contact details are legitimately shared after a match."""

    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    department: str
    phone: str | None = None


class TripOut(BaseModel):
    id: uuid.UUID
    ride_id: uuid.UUID
    status: TripStatus
    direction: RideDirection | None = None

    # --- journey snapshot (survives later edits to the ride) ---
    meeting_point: str | None = None
    meeting_location: GeoPoint | None = None
    departure_at: datetime | None = None
    pickup_area: str | None = None
    destination_area: str | None = None
    vehicle: VehicleSummary | None = None
    fuel_preference: FuelPreference | None = None

    # --- participants ---
    driver: DriverSummary
    passenger: RequesterSummary
    counterpart: CounterpartOut
    driver_phone: str | None = None
    passenger_phone: str | None = None

    conversation_id: uuid.UUID | None = None

    # --- lifecycle ---
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by_id: uuid.UUID | None = None
    cancellation_reason: str | None = None
    driver_confirmed_complete: bool = False
    passenger_confirmed_complete: bool = False
    awaiting_my_confirmation: bool = False

    # --- reviews (Phase 7) ---
    can_review: bool = False
    viewer_reviewed: bool = False

    # --- what this viewer may do next ---
    my_role: str = "PASSENGER"
    can_start: bool = False
    can_complete: bool = False
    can_cancel: bool = False
    can_mark_no_show: bool = False

    created_at: datetime


class TripListOut(BaseModel):
    items: list[TripOut]
    count: int


class TripActionIn(BaseModel):
    """Reason/note attached to a cancel, no-show or completion."""

    reason: str | None = Field(default=None, max_length=300)
