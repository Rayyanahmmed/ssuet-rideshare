"""Domain enumerations shared by the ORM models and the API schemas.

They are persisted as VARCHAR with a CHECK-style validation at the Python layer
(`native_enum=False`) so the same migration runs on PostgreSQL and SQLite.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # nicer logging / JSON output
        return self.value


class UserRole(StrEnum):
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class VerificationType(StrEnum):
    UNIVERSITY_EMAIL = "UNIVERSITY_EMAIL"
    STUDENT_ID = "STUDENT_ID"
    EMPLOYEE_ID = "EMPLOYEE_ID"
    MANUAL = "MANUAL"


class VehicleType(StrEnum):
    CAR = "CAR"
    BIKE = "BIKE"


class VehicleStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class RideDirection(StrEnum):
    HOME_TO_UNIVERSITY = "HOME_TO_UNIVERSITY"
    UNIVERSITY_TO_HOME = "UNIVERSITY_TO_HOME"


class FuelPreference(StrEnum):
    FREE = "FREE"
    SHARE_FUEL = "SHARE_FUEL"


class ContributionType(StrEnum):
    NONE = "NONE"
    FIXED = "FIXED"
    EXPECTED = "EXPECTED"
    NEGOTIABLE = "NEGOTIABLE"


class RideStatus(StrEnum):
    OPEN = "OPEN"
    MATCHED = "MATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class RideRequestStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class TripStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class NotificationType(StrEnum):
    RIDE_REQUEST_RECEIVED = "RIDE_REQUEST_RECEIVED"
    RIDE_REQUEST_ACCEPTED = "RIDE_REQUEST_ACCEPTED"
    RIDE_REQUEST_REJECTED = "RIDE_REQUEST_REJECTED"
    RIDE_CANCELLED = "RIDE_CANCELLED"
    TRIP_CANCELLED = "TRIP_CANCELLED"
    NEW_MESSAGE = "NEW_MESSAGE"
    TRIP_REMINDER = "TRIP_REMINDER"
    TRIP_STARTED = "TRIP_STARTED"
    TRIP_AWAITING_CONFIRMATION = "TRIP_AWAITING_CONFIRMATION"
    TRIP_NO_SHOW = "TRIP_NO_SHOW"
    TRIP_COMPLETED = "TRIP_COMPLETED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    DRIVER_ARRIVED = "DRIVER_ARRIVED"
    PAYMENT_MARKED_PAID = "PAYMENT_MARKED_PAID"
    ACCOUNT_VERIFIED = "ACCOUNT_VERIFIED"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_REACTIVATED = "ACCOUNT_REACTIVATED"
    VEHICLE_VERIFIED = "VEHICLE_VERIFIED"
    VEHICLE_REJECTED = "VEHICLE_REJECTED"
    NEW_REVIEW = "NEW_REVIEW"
    REPORT_RECEIVED = "REPORT_RECEIVED"
    REPORT_RESOLVED = "REPORT_RESOLVED"
    PHOTO_REMOVED = "PHOTO_REMOVED"
    SYSTEM = "SYSTEM"


class ReportCategory(StrEnum):
    INAPPROPRIATE_BEHAVIOR = "INAPPROPRIATE_BEHAVIOR"
    FAKE_PROFILE = "FAKE_PROFILE"
    MISLEADING_RIDE = "MISLEADING_RIDE"
    HARASSMENT = "HARASSMENT"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    NON_PAYMENT = "NON_PAYMENT"  # Payment feature: driver reports a passenger who did not pay
    MISCOMMITMENT = "MISCOMMITMENT"  # a member did not keep the agreed ride or meeting
    SCAM_OR_FRAUD = "SCAM_OR_FRAUD"  # fake payment claim, fake ride or any other scam
    PROFILE_PHOTO = "PROFILE_PHOTO"  # Phase 15 — the picture, not the behaviour
    OTHER = "OTHER"


class PhotoReportReason(StrEnum):
    """Why a profile photo was reported (Phase 15)."""

    OFFENSIVE = "OFFENSIVE"
    NOT_A_REAL_PERSON = "NOT_A_REAL_PERSON"
    IMPERSONATION = "IMPERSONATION"
    OTHER = "OTHER"


PHOTO_REPORT_REASON_LABELS: dict[str, str] = {
    "OFFENSIVE": "Offensive or explicit",
    "NOT_A_REAL_PERSON": "Not a photo of a person",
    "IMPERSONATION": "Someone else's photo",
    "OTHER": "Something else",
}


class PaymentStatus(StrEnum):
    """Cash fuel payment for a completed trip (payment feature).

    PENDING is implicit (no row yet). The driver either confirms the cash was
    received (VERIFIED, invoice issued) or reports that it was not paid
    (NON_PAYMENT_REPORTED, a report is opened for the admin office).
    """

    PENDING = "PENDING"
    PAID_BY_PASSENGER = "PAID_BY_PASSENGER"  # passenger says cash was paid; driver must verify
    VERIFIED = "VERIFIED"
    NON_PAYMENT_REPORTED = "NON_PAYMENT_REPORTED"


class ReportStatus(StrEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class AdminActionType(StrEnum):
    VERIFY_USER = "VERIFY_USER"
    REJECT_USER_VERIFICATION = "REJECT_USER_VERIFICATION"
    SUSPEND_USER = "SUSPEND_USER"
    REACTIVATE_USER = "REACTIVATE_USER"
    VERIFY_VEHICLE = "VERIFY_VEHICLE"
    REJECT_VEHICLE = "REJECT_VEHICLE"
    UPDATE_REPORT = "UPDATE_REPORT"
    REMOVE_PROFILE_PHOTO = "REMOVE_PROFILE_PHOTO"
    CANCEL_RIDE = "CANCEL_RIDE"
    HIDE_REVIEW = "HIDE_REVIEW"
    UNHIDE_REVIEW = "UNHIDE_REVIEW"
    UPDATE_SETTINGS = "UPDATE_SETTINGS"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Allowed status transitions (§10) — enforced by services, documented here.
# ---------------------------------------------------------------------------
RIDE_STATUS_TRANSITIONS: dict[RideStatus, set[RideStatus]] = {
    RideStatus.OPEN: {RideStatus.MATCHED, RideStatus.CANCELLED, RideStatus.EXPIRED},
    RideStatus.MATCHED: {RideStatus.IN_PROGRESS, RideStatus.CANCELLED, RideStatus.OPEN},
    RideStatus.IN_PROGRESS: {RideStatus.COMPLETED, RideStatus.CANCELLED},
    RideStatus.COMPLETED: set(),
    RideStatus.CANCELLED: set(),
    RideStatus.EXPIRED: set(),
}

TRIP_STATUS_TRANSITIONS: dict[TripStatus, set[TripStatus]] = {
    TripStatus.CONFIRMED: {TripStatus.IN_PROGRESS, TripStatus.CANCELLED, TripStatus.NO_SHOW},
    TripStatus.IN_PROGRESS: {TripStatus.COMPLETED, TripStatus.CANCELLED},
    TripStatus.COMPLETED: set(),
    TripStatus.CANCELLED: set(),
    TripStatus.NO_SHOW: set(),
}
