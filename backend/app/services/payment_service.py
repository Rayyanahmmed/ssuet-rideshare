"""Cash payment record and invoice for a completed trip (payment feature).

Rules encoded here:

* Only a **completed** trip can be settled. The payment is for the fuel share of a
  journey that actually happened, so it comes after both members confirm the trip.
* Only the **driver** records the outcome. The passenger cannot mark their own
  payment as received.
* A trip is settled **once**. After VERIFIED or NON_PAYMENT_REPORTED, no further
  change is accepted from the driver. This keeps the evidence stable.
* A non-payment report is a normal `Report` (category NON_PAYMENT) against the
  passenger. It enters the same admin queue as every other report and reaches the
  admin's notifications.
* The invoice is visible to both participants, but only after verification.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import (
    AccountStatus,
    PaymentStatus,
    ReportCategory,
    ReportStatus,
    TripStatus,
    UserRole,
)
from app.models.payment import TripPayment
from app.models.report import Report
from app.models.trip import Trip
from app.models.user import User
from app.schemas.payment import InvoiceOut, PaymentOut
from app.services.notification_service import create_notification_from_template
from app.services.trip_service import get_trip_or_404, load_trip_for

logger = logging.getLogger("ssuet.rideshare.payments")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _payment_for(db: Session, trip: Trip) -> TripPayment | None:
    return db.scalar(select(TripPayment).where(TripPayment.trip_id == trip.id))


def _payment_out(trip: Trip, payment: TripPayment | None) -> PaymentOut:
    if payment is None:
        return PaymentOut(trip_id=trip.id, status=PaymentStatus.PENDING)
    return PaymentOut(
        trip_id=trip.id,
        status=payment.status,
        amount_pkr=payment.amount_pkr,
        invoice_number=payment.invoice_number,
        verified_at=_aware(payment.verified_at),
        non_payment_report_id=payment.non_payment_report_id,
    )


def payment_window_open(trip: Trip) -> bool:
    """Cash payment opens when the journey starts and stays open after it completes."""

    return trip.status in (TripStatus.IN_PROGRESS, TripStatus.COMPLETED)


def payment_settled(payment: TripPayment | None) -> bool:
    """A payment the driver has either verified or reported. Only then can the trip be finished."""

    return payment is not None and payment.status in (
        PaymentStatus.VERIFIED,
        PaymentStatus.NON_PAYMENT_REPORTED,
    )


def _require_open_window(trip: Trip) -> None:
    if not payment_window_open(trip):
        raise ConflictError("The cash payment opens once the journey has started.")


def _require_driver(trip: Trip, actor: User) -> None:
    if trip.driver_id != actor.id:
        raise ForbiddenError("Only the driver can do this for the trip.")


def _require_driver_of_completed_trip(db: Session, trip_id: uuid.UUID, actor: User) -> Trip:
    trip = get_trip_or_404(db, trip_id)
    _require_driver(trip, actor)
    _require_open_window(trip)
    return trip


def _ensure_not_settled(payment: TripPayment | None) -> None:
    if payment is None:
        return
    if payment.status is PaymentStatus.VERIFIED:
        raise ConflictError("This payment is already verified.")
    if payment.status is PaymentStatus.NON_PAYMENT_REPORTED:
        raise ConflictError(
            "A non-payment report is already open for this trip. The ride-share office will review it."
        )


def _invoice_number(trip: Trip, verified_at: datetime) -> str:
    return f"SRS-{verified_at:%Y%m%d}-{trip.id.hex[:8].upper()}"


def get_payment(db: Session, trip_id: uuid.UUID, viewer: User) -> PaymentOut:
    trip = load_trip_for(db, trip_id, viewer)
    return _payment_out(trip, _payment_for(db, trip))


def confirm_cash_payment(
    db: Session, trip_id: uuid.UUID, driver: User, amount_pkr: int | None = None
) -> PaymentOut:
    """Driver confirms the cash was received → VERIFIED, invoice issued."""

    trip = _require_driver_of_completed_trip(db, trip_id, driver)
    payment = _payment_for(db, trip)
    _ensure_not_settled(payment)

    now = _utcnow()
    if payment is None:
        payment = TripPayment(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            passenger_id=trip.passenger_id,
        )
        db.add(payment)
    payment.status = PaymentStatus.VERIFIED
    payment.amount_pkr = amount_pkr
    payment.verified_at = now
    payment.invoice_number = _invoice_number(trip, now)
    db.flush()

    ride = trip.ride
    create_notification_from_template(
        db,
        user_id=trip.passenger_id,
        template="PAYMENT_CONFIRMED",
        commit=False,
        driver_name=driver.full_name,
        area=ride.pickup_area if ride is not None else "",
        invoice_number=payment.invoice_number,
        data={"screen": "trip", "trip_id": str(trip.id)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This payment was already recorded. Refresh the trip to see its status.") from None
    db.refresh(payment)
    logger.info("cash payment verified for trip %s, invoice %s", trip.id, payment.invoice_number)
    return _payment_out(trip, payment)


def mark_paid_by_passenger(db: Session, trip_id: uuid.UUID, passenger: User) -> PaymentOut:
    """Passenger says the cash fuel share has been paid → PAID_BY_PASSENGER.

    This does not create an invoice. The driver must confirm the cash was received
    (or report it), so neither side can settle the payment alone.
    """

    trip = get_trip_or_404(db, trip_id)
    if trip.passenger_id != passenger.id:
        raise ForbiddenError("Only the passenger can mark their payment as done.")
    _require_open_window(trip)
    payment = _payment_for(db, trip)
    if payment is not None:
        if payment.status is PaymentStatus.PAID_BY_PASSENGER:
            raise ConflictError("You have already marked this payment as done. The driver will confirm it.")
        _ensure_not_settled(payment)

    if payment is None:
        payment = TripPayment(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            passenger_id=trip.passenger_id,
        )
        db.add(payment)
    payment.status = PaymentStatus.PAID_BY_PASSENGER

    create_notification_from_template(
        db,
        user_id=trip.driver_id,
        template="PAYMENT_MARKED_PAID",
        commit=False,
        passenger_name=passenger.full_name,
        data={"screen": "trip", "trip_id": str(trip.id)},
    )
    db.commit()
    db.refresh(payment)
    logger.info("passenger marked payment done for trip %s", trip.id)
    return _payment_out(trip, payment)


def report_non_payment(
    db: Session, trip_id: uuid.UUID, driver: User, description: str
) -> PaymentOut:
    """Driver reports that the passenger did not pay → NON_PAYMENT_REPORTED + Report."""

    trip = _require_driver_of_completed_trip(db, trip_id, driver)
    payment = _payment_for(db, trip)
    _ensure_not_settled(payment)

    report = Report(
        reporter_id=driver.id,
        reported_user_id=trip.passenger_id,
        trip_id=trip.id,
        ride_id=trip.ride_id,
        category=ReportCategory.NON_PAYMENT,
        description=" ".join(description.split()),
        status=ReportStatus.OPEN,
    )
    db.add(report)
    db.flush()

    if payment is None:
        payment = TripPayment(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            passenger_id=trip.passenger_id,
        )
        db.add(payment)
    payment.status = PaymentStatus.NON_PAYMENT_REPORTED
    payment.non_payment_report_id = report.id
    db.flush()

    create_notification_from_template(
        db,
        user_id=driver.id,
        template="REPORT_RECEIVED",
        commit=False,
        data={"report_id": str(report.id)},
        reported_name=trip.passenger.full_name.split(" ")[0],
    )
    admins = db.scalars(
        select(User).where(User.role == UserRole.ADMIN, User.account_status == AccountStatus.ACTIVE)
    ).all()
    for admin in admins:
        create_notification_from_template(
            db,
            user_id=admin.id,
            template="ADMIN_NEW_REPORT",
            commit=False,
            data={"report_id": str(report.id)},
            reporter_name=driver.full_name,
            reported_name=trip.passenger.full_name,
            category=ReportCategory.NON_PAYMENT.value,
        )
    db.commit()
    db.refresh(payment)
    logger.info("non-payment report %s opened for trip %s", report.id, trip.id)
    return _payment_out(trip, payment)


def get_invoice(db: Session, trip_id: uuid.UUID, viewer: User) -> InvoiceOut:
    """Invoice for a verified payment. Only the two participants (or an admin)."""

    trip = load_trip_for(db, trip_id, viewer)
    payment = _payment_for(db, trip)
    if payment is None or payment.status is not PaymentStatus.VERIFIED or payment.invoice_number is None:
        raise NotFoundError("No verified payment exists for this trip yet, so there is no invoice.")

    ride = trip.ride
    return InvoiceOut(
        invoice_number=payment.invoice_number,
        trip_id=trip.id,
        issued_at=_aware(payment.verified_at) or _utcnow(),
        amount_pkr=payment.amount_pkr,
        status=payment.status,
        driver_name=trip.driver.full_name,
        passenger_name=trip.passenger.full_name,
        pickup_area=ride.pickup_area if ride is not None else None,
        destination_area=ride.destination_area if ride is not None else None,
        departure_at=_aware(ride.departure_at) if ride is not None else None,
        completed_at=_aware(trip.completed_at),
    )
