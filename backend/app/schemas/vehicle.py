"""Vehicle contracts (§5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.enums import VehicleStatus, VehicleType
from app.schemas.common import ORMModel


class VehicleCreateIn(BaseModel):
    vehicle_type: VehicleType
    make_and_model: str = Field(min_length=2, max_length=120, examples=["Toyota Corolla 2019"])
    color: str = Field(min_length=2, max_length=60, examples=["White"])
    registration_number: str = Field(min_length=3, max_length=40, examples=["ABC-1234"])
    passenger_capacity: int = Field(default=1, ge=1, le=8)
    # Uploaded files (Phase 10) — see POST /uploads/vehicle. The legacy external link
    # is still accepted so existing members are not forced to re-enter their vehicle.
    photo_asset_id: uuid.UUID | None = Field(
        default=None, description="id returned by POST /uploads/vehicle (photo of the car)"
    )
    registration_asset_id: uuid.UUID | None = Field(
        default=None, description="id returned by POST /uploads/vehicle (registration book)"
    )
    vehicle_photo_url: HttpUrl | None = None
    is_primary: bool = True

    @field_validator("make_and_model", "color", "registration_number")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("registration_number")
    @classmethod
    def _normalise_registration(cls, value: str) -> str:
        return value.upper().replace(" ", "-")


class VehicleUpdateIn(BaseModel):
    make_and_model: str | None = Field(default=None, min_length=2, max_length=120)
    color: str | None = Field(default=None, min_length=2, max_length=60)
    registration_number: str | None = Field(default=None, min_length=3, max_length=40)
    passenger_capacity: int | None = Field(default=None, ge=1, le=8)
    photo_asset_id: uuid.UUID | None = None
    registration_asset_id: uuid.UUID | None = None
    vehicle_photo_url: HttpUrl | None = None
    is_primary: bool | None = None


class VehicleOwnerOut(ORMModel):
    """Owner view — includes the registration number, which strangers never see."""

    id: uuid.UUID
    vehicle_type: VehicleType
    make_and_model: str
    color: str
    registration_number: str
    passenger_capacity: int
    vehicle_photo_url: str | None = None
    photo_asset_id: uuid.UUID | None = None
    registration_asset_id: uuid.UUID | None = None
    is_primary: bool
    status: VehicleStatus
    review_note: str | None = None
    created_at: datetime


class VehiclePublicOut(BaseModel):
    """What other members see on a ride card / details page."""

    vehicle_type: VehicleType
    make_and_model: str
    color: str
    is_verified: bool
