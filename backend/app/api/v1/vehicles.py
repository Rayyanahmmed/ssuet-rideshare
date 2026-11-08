"""Vehicle endpoints — `/api/v1/vehicles` (§5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import MessageOut
from app.schemas.vehicle import VehicleCreateIn, VehicleOwnerOut, VehicleUpdateIn
from app.services import vehicle_service

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get("", response_model=list[VehicleOwnerOut], summary="My vehicles")
def list_vehicles(current_user: CurrentUser, db: DbSession) -> list[VehicleOwnerOut]:
    return [VehicleOwnerOut.model_validate(v) for v in vehicle_service.list_my_vehicles(db, current_user)]


@router.post(
    "",
    response_model=VehicleOwnerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a car or bike",
    description="New vehicles start as PENDING and are reviewed by an administrator.",
)
def create_vehicle(
    payload: VehicleCreateIn, current_user: CurrentUser, db: DbSession
) -> VehicleOwnerOut:
    vehicle = vehicle_service.create_vehicle(db, current_user, payload)
    return VehicleOwnerOut.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOwnerOut, summary="Update a vehicle")
def update_vehicle(
    vehicle_id: uuid.UUID, payload: VehicleUpdateIn, current_user: CurrentUser, db: DbSession
) -> VehicleOwnerOut:
    vehicle = vehicle_service.get_owned_vehicle(db, vehicle_id, current_user)
    return VehicleOwnerOut.model_validate(vehicle_service.update_vehicle(db, vehicle, payload))


@router.delete("/{vehicle_id}", response_model=MessageOut, summary="Remove a vehicle")
def delete_vehicle(vehicle_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MessageOut:
    vehicle = vehicle_service.get_owned_vehicle(db, vehicle_id, current_user)
    vehicle_service.delete_vehicle(db, vehicle)
    return MessageOut(message="Vehicle removed.")
