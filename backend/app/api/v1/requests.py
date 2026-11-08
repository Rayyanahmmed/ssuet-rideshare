"""Ride-request endpoints — `/api/v1/requests` and `/api/v1/rides/{id}/requests` (§9)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, VerifiedUser
from app.core.exceptions import NotFoundError
from app.models.enums import RideRequestStatus
from app.models.ride import RideRequest
from app.schemas.common import MessageOut
from app.schemas.ride import (
    MyRequestsOut,
    RequesterSummary,
    RideRequestCreateIn,
    RideRequestForDriverOut,
    RideRequestForPassengerOut,
    RequestOut,
)
from app.schemas.trip import TripOut
from app.services import request_service, ride_service, trip_service

router = APIRouter(prefix="/requests", tags=["Ride requests"])
ride_router = APIRouter(prefix="/rides", tags=["Ride requests"])


def _requester(user) -> RequesterSummary:
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


@router.get("/mine", response_model=MyRequestsOut, summary="Requests I sent")
def my_requests(
    current_user: CurrentUser,
    db: DbSession,
    request_status: RideRequestStatus | None = Query(default=None, alias="status"),
) -> MyRequestsOut:
    rows = request_service.list_my_requests(db, current_user, request_status)
    items = [
        RideRequestForPassengerOut(
            id=row.id,
            ride_id=row.ride_id,
            status=row.status,
            message=row.message,
            response_note=row.response_note,
            responded_at=row.responded_at,
            created_at=row.created_at,
            ride=ride_service.serialize_ride(row.ride, current_user, my_request=row, detail=False),
        )
        for row in rows
        if row.ride is not None
    ]
    return MyRequestsOut(items=items, count=len(items))


@router.post("/{request_id}/cancel", response_model=RequestOut, summary="Withdraw a pending request")
def cancel_request(request_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> RequestOut:
    request = db.get(RideRequest, request_id)
    if request is None:
        raise NotFoundError("This request could not be found.")
    return RequestOut.model_validate(request_service.cancel_request(db, request, current_user))


# ---------------------------------------------------------------- passenger
@ride_router.post(
    "/{ride_id}/requests",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ask to join a journey",
    responses={
        403: {"description": "Account not verified, or blocked pair"},
        404: {"description": "Ride not found"},
        409: {"description": "Already requested / ride no longer available"},
    },
)
def create_request(
    ride_id: uuid.UUID,
    payload: RideRequestCreateIn,
    current_user: VerifiedUser,
    db: DbSession,
) -> RequestOut:
    request = request_service.create_request(db, current_user, ride_id, payload.message)
    return RequestOut.model_validate(request)


# ------------------------------------------------------------------- driver
@ride_router.get(
    "/{ride_id}/requests",
    response_model=list[RideRequestForDriverOut],
    summary="Request inbox for one of my journeys",
)
def ride_requests(
    ride_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> list[RideRequestForDriverOut]:
    ride = ride_service.get_ride(db, ride_id)
    rows = request_service.list_requests_for_ride(db, ride, current_user)
    return [
        RideRequestForDriverOut(
            id=row.id,
            ride_id=row.ride_id,
            status=row.status,
            message=row.message,
            response_note=row.response_note,
            responded_at=row.responded_at,
            created_at=row.created_at,
            passenger=_requester(row.passenger),
            ride_pickup_area=ride.pickup_area,
            ride_departure_at=ride.departure_at,
        )
        for row in rows
    ]


@router.get(
    "/inbox",
    response_model=list[RideRequestForDriverOut],
    summary="All requests received across my journeys",
)
def driver_inbox(current_user: CurrentUser, db: DbSession) -> list[RideRequestForDriverOut]:
    rows = request_service.list_requests_for_driver(db, current_user)
    return [
        RideRequestForDriverOut(
            id=row.id,
            ride_id=row.ride_id,
            status=row.status,
            message=row.message,
            response_note=row.response_note,
            responded_at=row.responded_at,
            created_at=row.created_at,
            passenger=_requester(row.passenger),
            ride_pickup_area=row.ride.pickup_area if row.ride else "",
            ride_departure_at=row.ride.departure_at if row.ride else row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/{request_id}/accept",
    response_model=TripOut,
    summary="Accept a request and reserve the seat",
    description=(
        "Atomic: the ride row is locked, the seat is reserved, a trip and its private "
        "conversation are created, other pending requests are declined and both sides are "
        "notified — all in one transaction. Losing a concurrency race returns "
        "409 RIDE_NOT_AVAILABLE."
    ),
)
def accept_request(request_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TripOut:
    trip = request_service.accept_request(db, request_id, current_user)
    db.refresh(trip)
    return trip_service.serialize_trip(db, trip, current_user)


@router.post("/{request_id}/reject", response_model=RequestOut, summary="Decline a request")
def reject_request(
    request_id: uuid.UUID,
    payload: RideRequestCreateIn,
    current_user: CurrentUser,
    db: DbSession,
) -> RequestOut:
    request = request_service.reject_request(db, request_id, current_user, payload.message)
    return RequestOut.model_validate(request)
