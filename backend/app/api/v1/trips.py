"""Trip lifecycle endpoints — `/api/v1/trips` (§10, §11).

Everything here is participant-only: a trip exists because two members agreed to
travel together, and only those two (plus administrators) may read or change it.
Every response carries the actions the *current* viewer may take next, so the
mobile app never has to duplicate the state machine.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import TripStatus
from app.schemas.payment import InvoiceOut, PaymentConfirmIn, PaymentNonPaymentIn, PaymentOut
from app.schemas.trip import TripActionIn, TripListOut, TripOut
from app.services import payment_service, trip_service

router = APIRouter(prefix="/trips", tags=["Trips"])


@router.get(
    "/mine",
    response_model=TripListOut,
    summary="Trips I am part of (as driver or passenger)",
)
def list_my_trips(
    current_user: CurrentUser,
    db: DbSession,
    role: Literal["DRIVER", "PASSENGER"] | None = Query(default=None),
    trip_status: TripStatus | None = Query(default=None, alias="status"),
    upcoming: bool | None = Query(default=None, description="true = live trips, false = history"),
    limit: int = Query(default=50, ge=1, le=100),
) -> TripListOut:
    return trip_service.list_trips(
        db, current_user, role=role, status=trip_status, upcoming=upcoming, limit=limit
    )


@router.get("/{trip_id}", response_model=TripOut, summary="Trip detail")
def get_trip(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TripOut:
    trip = trip_service.load_trip_for(db, trip_id, current_user)
    return trip_service.serialize_trip(db, trip, current_user)


@router.post(
    "/{trip_id}/arrived",
    response_model=TripOut,
    summary='Driver says "I have arrived" at the meeting point (passenger is notified)',
    responses={403: {"description": "Not the driver"}, 409: {"description": "Too early or trip not active"}},
)
def mark_arrived(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TripOut:
    trip = trip_service.mark_arrived(db, trip_id, current_user)
    return trip_service.serialize_trip(db, trip, current_user)


@router.post(
    "/{trip_id}/start",
    response_model=TripOut,
    summary="Driver starts the journey",
    responses={
        403: {"description": "Not the driver"},
        409: {"description": "Trip cannot be started (already started / too early)"},
    },
)
def start_trip(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TripOut:
    trip = trip_service.start_trip(db, trip_id, current_user)
    return trip_service.serialize_trip(db, trip, current_user)


@router.post(
    "/{trip_id}/complete",
    response_model=TripOut,
    status_code=status.HTTP_200_OK,
    summary="Confirm the journey happened (both sides must confirm)",
    responses={409: {"description": "Trip not in progress or already confirmed by you"}},
)
def complete_trip(
    trip_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    payload: TripActionIn | None = None,
) -> TripOut:
    trip = trip_service.complete_trip(
        db, trip_id, current_user, note=payload.reason if payload else None
    )
    return trip_service.serialize_trip(db, trip, current_user)


@router.post(
    "/{trip_id}/cancel",
    response_model=TripOut,
    summary="Cancel a trip (passenger may cancel before departure only)",
    responses={409: {"description": "Trip already finished or already started"}},
)
def cancel_trip(
    trip_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    payload: TripActionIn | None = None,
) -> TripOut:
    trip = trip_service.cancel_trip(
        db, trip_id, current_user, reason=payload.reason if payload else None
    )
    return trip_service.serialize_trip(db, trip, current_user)


@router.post(
    "/{trip_id}/no-show",
    response_model=TripOut,
    summary="Driver records that the passenger never turned up",
    responses={403: {"description": "Not the driver"}, 409: {"description": "Too early or invalid state"}},
)
def mark_no_show(
    trip_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    payload: TripActionIn | None = None,
) -> TripOut:
    trip = trip_service.mark_no_show(
        db, trip_id, current_user, reason=payload.reason if payload else None
    )
    return trip_service.serialize_trip(db, trip, current_user)


# ----------------------------------------------------------- cash payment (payment)
@router.get(
    "/{trip_id}/payment",
    response_model=PaymentOut,
    summary="Cash payment status for a trip (participants only)",
)
def get_payment(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> PaymentOut:
    return payment_service.get_payment(db, trip_id, current_user)


@router.post(
    "/{trip_id}/payment/mark-paid",
    response_model=PaymentOut,
    summary="Passenger says the cash fuel share is paid (driver must then verify)",
    responses={
        403: {"description": "Not the passenger"},
        409: {"description": "Payment window not open, or already marked / settled"},
    },
)
def mark_paid(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> PaymentOut:
    return payment_service.mark_paid_by_passenger(db, trip_id, current_user)


@router.post(
    "/{trip_id}/payment/confirm",
    response_model=PaymentOut,
    summary="Driver confirms the cash was received (verified transaction + invoice)",
    responses={
        403: {"description": "Not the driver"},
        409: {"description": "Trip not completed, or payment already settled"},
    },
)
def confirm_payment(
    trip_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    payload: PaymentConfirmIn | None = None,
) -> PaymentOut:
    return payment_service.confirm_cash_payment(
        db, trip_id, current_user, amount_pkr=payload.amount_pkr if payload else None
    )


@router.post(
    "/{trip_id}/payment/non-payment-report",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Driver reports that the passenger did not pay (opens a report for the admin)",
    responses={
        403: {"description": "Not the driver"},
        409: {"description": "Trip not completed, or payment already settled"},
    },
)
def report_non_payment(
    trip_id: uuid.UUID,
    payload: PaymentNonPaymentIn,
    current_user: CurrentUser,
    db: DbSession,
) -> PaymentOut:
    return payment_service.report_non_payment(db, trip_id, current_user, payload.description)


@router.get(
    "/{trip_id}/invoice",
    response_model=InvoiceOut,
    summary="Invoice for a verified cash payment (participants only)",
    responses={404: {"description": "No verified payment yet"}},
)
def get_invoice(trip_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> InvoiceOut:
    return payment_service.get_invoice(db, trip_id, current_user)

