"""Vehicle registration & moderation (§5)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.enums import VehicleStatus
from app.models.media import PURPOSE_VEHICLE_DOCUMENT, MediaAsset
from app.models.ride import Ride
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreateIn, VehicleUpdateIn


def _resolve_upload(db: Session, owner: User, asset_id: uuid.UUID | None, label: str) -> uuid.UUID | None:
    """Accept an upload id only if it belongs to the caller and is a vehicle document."""
    if asset_id is None:
        return None
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.owner_id != owner.id:
        raise NotFoundError("This upload could not be found.")
    if asset.purpose != PURPOSE_VEHICLE_DOCUMENT:
        raise ValidationAppError(f"This upload cannot be used as the {label}.")
    return asset.id


def list_my_vehicles(db: Session, owner: User) -> list[Vehicle]:
    return list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.owner_id == owner.id, Vehicle.deleted_at.is_(None))
            .order_by(Vehicle.is_primary.desc(), Vehicle.created_at.desc())
        )
    )


def get_vehicle(db: Session, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFoundError("This vehicle could not be found.")
    return vehicle


def get_owned_vehicle(db: Session, vehicle_id: uuid.UUID, owner: User) -> Vehicle:
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle.owner_id != owner.id:
        raise ForbiddenError("This vehicle belongs to another member.")
    return vehicle


def create_vehicle(db: Session, owner: User, payload: VehicleCreateIn) -> Vehicle:
    duplicate = db.scalar(
        select(Vehicle.id).where(
            Vehicle.registration_number == payload.registration_number,
            Vehicle.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ValidationAppError(
            "A vehicle with this registration number is already registered.",
            details={"registration_number": "already registered"},
        )

    if payload.is_primary:
        # only one primary vehicle per owner
        for existing in list_my_vehicles(db, owner):
            existing.is_primary = False

    vehicle = Vehicle(
        owner_id=owner.id,
        vehicle_type=payload.vehicle_type,
        make_and_model=payload.make_and_model,
        color=payload.color,
        registration_number=payload.registration_number,
        passenger_capacity=payload.passenger_capacity,
        vehicle_photo_url=str(payload.vehicle_photo_url) if payload.vehicle_photo_url else None,
        photo_asset_id=_resolve_upload(db, owner, payload.photo_asset_id, "vehicle photo"),
        registration_asset_id=_resolve_upload(
            db, owner, payload.registration_asset_id, "registration document"
        ),
        is_primary=payload.is_primary,
        status=VehicleStatus.PENDING,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def update_vehicle(db: Session, vehicle: Vehicle, payload: VehicleUpdateIn) -> Vehicle:
    data = payload.model_dump(exclude_unset=True)

    if "registration_number" in data:
        data["registration_number"] = data["registration_number"].upper().replace(" ", "-")
        clash = db.scalar(
            select(Vehicle.id).where(
                Vehicle.registration_number == data["registration_number"],
                Vehicle.id != vehicle.id,
                Vehicle.deleted_at.is_(None),
            )
        )
        if clash is not None:
            raise ValidationAppError(
                "A vehicle with this registration number is already registered.",
                details={"registration_number": "already registered"},
            )

    if data.get("is_primary"):
        for existing in list_my_vehicles(db, vehicle.owner):
            if existing.id != vehicle.id:
                existing.is_primary = False

    # Changing identifying details sends the vehicle back to the verification queue.
    critical = {"registration_number", "make_and_model", "vehicle_type"}
    if critical & data.keys():
        vehicle.status = VehicleStatus.PENDING
        vehicle.reviewed_at = None
        vehicle.review_note = None

    for label, field in (("vehicle photo", "photo_asset_id"), ("registration document", "registration_asset_id")):
        if field in data:
            data[field] = _resolve_upload(db, vehicle.owner, data[field], label)

    for field, value in data.items():
        setattr(vehicle, field, str(value) if field == "vehicle_photo_url" and value else value)

    db.commit()
    db.refresh(vehicle)
    return vehicle


def delete_vehicle(db: Session, vehicle: Vehicle) -> None:
    used_by_open_ride = db.scalar(
        select(Ride.id).where(
            Ride.vehicle_id == vehicle.id,
            Ride.status.in_(["OPEN", "MATCHED", "IN_PROGRESS"]),
        )
    )
    if used_by_open_ride is not None:
        raise ValidationAppError(
            "This vehicle is used by a journey that is still open. Cancel or complete it first."
        )
    vehicle.deleted_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.commit()


# ------------------------------------------------------------------ helpers


def resolve_publish_vehicle(db: Session, driver: User, vehicle_id: uuid.UUID) -> Vehicle:
    """A driver may only publish with their own, non-rejected vehicle."""
    from app.core.config import settings

    vehicle = get_vehicle(db, vehicle_id)
    if vehicle.owner_id != driver.id:
        raise ForbiddenError("You can only publish rides with your own vehicle.")
    if vehicle.status is VehicleStatus.REJECTED:
        raise ValidationAppError(
            "This vehicle was rejected by an administrator and cannot be used for journeys.",
            details={"vehicle_id": "rejected"},
        )
    if settings.REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH and vehicle.status is not VehicleStatus.VERIFIED:
        raise ValidationAppError(
            "This vehicle is still awaiting verification. You can publish once an administrator approves it.",
            details={"vehicle_id": "pending"},
        )
    return vehicle
