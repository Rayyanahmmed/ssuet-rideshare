"""Cash payment and invoice contracts (payment feature).

The payment is made in cash between the two members. These schemas describe only
the record the driver keeps and the invoice that serves as evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import PaymentStatus

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 1000


class PaymentConfirmIn(BaseModel):
    """Driver confirms the cash was received. The amount is optional."""

    amount_pkr: int | None = Field(default=None, ge=0, le=100000)


class PaymentNonPaymentIn(BaseModel):
    """Driver reports that the passenger did not pay."""

    description: str = Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)


class PaymentOut(BaseModel):
    trip_id: uuid.UUID
    status: PaymentStatus
    amount_pkr: int | None = None
    invoice_number: str | None = None
    verified_at: datetime | None = None
    non_payment_report_id: uuid.UUID | None = None


class InvoiceOut(BaseModel):
    """Evidence document for a verified cash payment. Visible to both participants."""

    invoice_number: str
    trip_id: uuid.UUID
    issued_at: datetime
    payment_method: str = "CASH"
    amount_pkr: int | None = None
    status: PaymentStatus
    driver_name: str
    passenger_name: str
    pickup_area: str | None = None
    destination_area: str | None = None
    departure_at: datetime | None = None
    completed_at: datetime | None = None
    note: str = (
        "Cash fuel contribution recorded by the driver after the journey. "
        "The platform does not hold or move money."
    )
