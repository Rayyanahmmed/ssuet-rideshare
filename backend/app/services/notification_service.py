"""Notification persistence (§12).

Phase 2 only stores in-app notifications. Phase 5 adds Expo push fan-out on top
of the same rows, so nothing here has to change later.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.services import push_service

logger = logging.getLogger("ssuet.rideshare.notifications")


def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    commit: bool = True,
) -> Notification:
    """Persist one notification. The caller owns the surrounding transaction."""
    notification = Notification(
        user_id=user_id, type=type, title=title, body=body, data=data or {}
    )
    db.add(notification)
    # Queue the push for after commit — whether we own the transaction or not —
    # so nobody is notified about a row that ends up rolled back (§12).
    push_service.queue_push(db, notification)
    if commit:
        db.commit()
        db.refresh(notification)
    return notification


# --------------------------------------------------------------------------
# Templates (§12). Phase 5 fans these out to Expo push; Phase 3 only persists
# them so the in-app notification history is already real.
# --------------------------------------------------------------------------
TEMPLATES: dict[str, tuple[NotificationType, str, str]] = {
    "RIDE_REQUEST_RECEIVED": (
        NotificationType.RIDE_REQUEST_RECEIVED,
        "New ride request",
        "{passenger_name} wants to join your ride from {area}.",
    ),
    "RIDE_REQUEST_ACCEPTED": (
        NotificationType.RIDE_REQUEST_ACCEPTED,
        "Request accepted",
        "{driver_name} accepted your request for the {area} journey. Chat is now open.",
    ),
    "RIDE_REQUEST_REJECTED": (
        NotificationType.RIDE_REQUEST_REJECTED,
        "Request declined",
        "{driver_name} could not take you this time for the {area} journey.",
    ),
    "RIDE_CANCELLED": (
        NotificationType.RIDE_CANCELLED,
        "Journey cancelled",
        "The {area} journey was cancelled. Reason: {reason}",
    ),
    "TRIP_CANCELLED": (
        NotificationType.TRIP_CANCELLED,
        "Trip cancelled",
        "{driver_name} cancelled your trip from {area}. Reason: {reason}",
    ),
    "NEW_MESSAGE": (
        NotificationType.NEW_MESSAGE,
        "New message",
        "{sender_name}: {preview}",
    ),
    "ACCOUNT_VERIFIED": (
        NotificationType.ACCOUNT_VERIFIED,
        "Account verified",
        "Your SSUET membership is verified{name_suffix}. You can now publish and request rides.",
    ),
    "ACCOUNT_SUSPENDED": (
        NotificationType.ACCOUNT_SUSPENDED,
        "Account suspended",
        "Your account has been suspended. Reason: {reason}. Contact the ride-share office to appeal.",
    ),
    "ACCOUNT_REACTIVATED": (
        NotificationType.ACCOUNT_REACTIVATED,
        "Account reactivated",
        "Welcome back — your account is active again and you can use SSUET RideShare normally.",
    ),
    "VEHICLE_VERIFIED": (
        NotificationType.VEHICLE_VERIFIED,
        "Vehicle verified",
        "{vehicle} is now verified and can be used for published journeys.",
    ),
    "VEHICLE_REJECTED": (
        NotificationType.VEHICLE_REJECTED,
        "Vehicle needs attention",
        "{vehicle} could not be verified. Reason: {reason}",
    ),
    "NEW_REVIEW": (
        NotificationType.NEW_REVIEW,
        "New rating",
        "{reviewer_name} rated your trip {rating} out of 5.",
    ),
    "REPORT_RECEIVED": (
        NotificationType.REPORT_RECEIVED,
        "Report received",
        "We have your report about {reported_name}. The ride-share office will review it.",
    ),
    "REPORT_RESOLVED": (
        NotificationType.REPORT_RESOLVED,
        "Report update",
        "Your report about {reported_name} is now {status}. {note}",
    ),
    "ADMIN_NEW_REPORT": (
        NotificationType.SYSTEM,
        "New report filed",
        "{reporter_name} reported {reported_name} ({category}).",
    ),
    "PHOTO_REMOVED": (
        NotificationType.PHOTO_REMOVED,
        "Profile photo removed",
        "An administrator removed your profile photo after a report. You can upload a different one.",
    ),
    "ADMIN_NEW_PHOTO_REPORT": (
        NotificationType.SYSTEM,
        "Profile photo reported",
        "{reporter_name} reported {reported_name}'s photo ({reason}).",
    ),
    "ADMIN_NEW_REVIEW_FLAGGED": (
        NotificationType.SYSTEM,
        "Review hidden",
        "A review on trip {trip} was hidden after moderation.",
    ),
    "TRIP_STARTED": (
        NotificationType.TRIP_STARTED,
        "Journey started",
        "{driver_name} has started the journey from {area}. Meet at the agreed point.",
    ),
    "TRIP_AWAITING_CONFIRMATION": (
        NotificationType.TRIP_AWAITING_CONFIRMATION,
        "Confirm your trip",
        "{driver_name} marked the {area} journey as finished. Please confirm on your side.",
    ),
    "TRIP_NO_SHOW": (
        NotificationType.TRIP_NO_SHOW,
        "Marked as no-show",
        "The driver recorded that you did not join the {area} journey. Reason: {reason}",
    ),
    "TRIP_COMPLETED": (
        NotificationType.TRIP_COMPLETED,
        "Trip completed",
        "Your trip with {counterpart_name} from {area} is complete. You can rate them now.",
    ),
    "PAYMENT_CONFIRMED": (
        NotificationType.PAYMENT_CONFIRMED,
        "Payment verified",
        "{driver_name} confirmed your cash payment for the trip from {area}. Invoice {invoice_number} is ready.",
    ),
}


def create_notification_from_template(
    db: Session,
    *,
    user_id: uuid.UUID,
    template: str,
    commit: bool = True,
    data: dict[str, Any] | None = None,
    **context: Any,
) -> Notification:
    """Render a templated notification. Unknown keys are ignored safely."""
    type_, title, body_template = TEMPLATES[template]
    try:
        body = body_template.format(**context)
    except KeyError:  # defensive: never fail a business action over copy
        body = body_template
    return create_notification(
        db, user_id=user_id, type=type_, title=title, body=body, data=data, commit=commit
    )
