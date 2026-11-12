"""Cash payment record for a completed trip — the evidence behind an invoice.

The platform does not move money. Passenger and driver settle the fuel
contribution in cash, and the driver records the outcome here:

* VERIFIED — the driver confirmed the cash was received. An invoice number is
  issued and the passenger can see the verified transaction.
* NON_PAYMENT_REPORTED — the driver says the passenger did not pay. A `Report`
  (category NON_PAYMENT) is opened and linked, so the admin office handles it in
  the normal reports queue.

One row per trip (unique `trip_id`); a trip can be settled only once.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import PaymentStatus

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.trip import Trip
    from app.models.user import User


class TripPayment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "trip_payments"
    __table_args__ = (
        UniqueConstraint("trip_id", name="uq_trip_payments_trip_id"),
        UniqueConstraint("invoice_number", name="uq_trip_payments_invoice_number"),
        CheckConstraint("amount_pkr IS NULL OR amount_pkr >= 0", name="payment_amount_non_negative"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passenger_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus, 32), nullable=False, default=PaymentStatus.PENDING
    )
    #: Cash amount the driver recorded, in whole rupees (optional).
    amount_pkr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    non_payment_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )

    trip: Mapped[Trip] = relationship(foreign_keys=[trip_id])
    driver: Mapped[User] = relationship(foreign_keys=[driver_id])
    passenger: Mapped[User] = relationship(foreign_keys=[passenger_id])
    non_payment_report: Mapped[Report | None] = relationship(foreign_keys=[non_payment_report_id])
