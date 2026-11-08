"""Ratings & reviews (§14).

Rules encoded here — and, where possible, also by the database:

* only the **two participants of a completed trip** may review each other;
* **one review per author per trip** (`uq_reviews_trip_author`), and the trip row
  keeps a per-side flag so the UI can hide the button without reading reviews;
* a rating is an integer **1–5**; the comment is optional but trimmed, and a
  one-character "comment" is rejected rather than stored;
* the subject's `rating_average` / `rating_count` are **recomputed from the table**
  on every write (and on moderation), never incremented by hand — so they can
  never drift, and hidden reviews drop out of the average;
* the subject is notified, without ever exposing the author's contact details.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import TripStatus
from app.models.review import Review
from app.models.trip import Trip
from app.models.user import User
from app.schemas.review import (
    PendingReviewListOut,
    PendingReviewOut,
    ReviewAuthorOut,
    ReviewOut,
    ReviewPage,
)
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.reviews")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _author_out(user: User) -> ReviewAuthorOut:
    return ReviewAuthorOut(
        id=user.id,
        full_name=user.full_name,
        profile_photo_url=user.photo_url,
        role=user.role,
        department=user.department,
    )


def _review_out(review: Review) -> ReviewOut:
    ride = review.trip.ride if review.trip is not None else None
    return ReviewOut(
        id=review.id,
        trip_id=review.trip_id,
        rating=review.rating,
        comment=review.comment,
        direction=ride.direction if ride else None,
        pickup_area=ride.pickup_area if ride else None,
        destination_area=ride.destination_area if ride else None,
        author=_author_out(review.author),
        subject_id=review.subject_id,
        created_at=review.created_at,
    )


def recompute_rating(db: Session, user_id: uuid.UUID) -> tuple[float, int]:
    """Rebuild a member's aggregate rating from the visible reviews.

    Recomputation (rather than `+=`) keeps the denormalised columns honest even
    after a review is hidden by an administrator or removed by a cascade.
    """

    visible = (Review.subject_id == user_id, Review.is_hidden.is_(False))
    average = db.scalar(select(func.avg(Review.rating)).where(*visible))
    count = db.scalar(select(func.count()).select_from(Review).where(*visible))
    user = db.get(User, user_id)
    if user is not None:
        user.rating_average = round(float(average or 0.0), 2)
        user.rating_count = int(count or 0)
    return round(float(average or 0.0), 2), int(count or 0)


# --------------------------------------------------------------------- create
def create_review(
    db: Session,
    author: User,
    *,
    trip_id: uuid.UUID,
    rating: int,
    comment: str | None = None,
) -> ReviewOut:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")

    if not trip.involves(author.id):
        # 404-style wording on purpose: a stranger should not learn that the id exists.
        raise ForbiddenError("You were not part of this trip.")

    if trip.status is not TripStatus.COMPLETED:
        raise ConflictError("You can rate this trip once it is completed.")

    is_driver = author.id == trip.driver_id
    already_reviewed = (
        trip.driver_reviewed_passenger if is_driver else trip.passenger_reviewed_driver
    )
    if already_reviewed:
        raise ConflictError("You have already rated this trip.")

    subject = trip.passenger if is_driver else trip.driver
    review = Review(
        trip_id=trip.id,
        author_id=author.id,
        subject_id=subject.id,
        rating=rating,
        comment=comment or None,
    )
    db.add(review)
    if is_driver:
        trip.driver_reviewed_passenger = True
    else:
        trip.passenger_reviewed_driver = True

    try:
        db.flush()
    except IntegrityError:  # two devices submitting at the same moment
        db.rollback()
        raise ConflictError("You have already rated this trip.") from None

    recompute_rating(db, subject.id)
    create_notification_from_template(
        db,
        user_id=subject.id,
        template="NEW_REVIEW",
        commit=False,
        data={"trip_id": str(trip.id), "review_id": str(review.id)},
        reviewer_name=author.full_name.split(" ")[0],
        rating=rating,
    )
    db.commit()
    db.refresh(review)
    return _review_out(review)


# ----------------------------------------------------------------------- read
def list_user_reviews(
    db: Session, user_id: uuid.UUID, *, page: int = 1, limit: int = 20
) -> ReviewPage:
    """Visible reviews about a member — readable by any signed-in member."""

    if db.get(User, user_id) is None:
        raise NotFoundError("This member could not be found.")

    base = select(Review).where(Review.subject_id == user_id, Review.is_hidden.is_(False))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)

    rows = db.scalars(
        base.options(joinedload(Review.author))
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    breakdown_rows = db.execute(
        select(Review.rating, func.count())
        .where(Review.subject_id == user_id, Review.is_hidden.is_(False))
        .group_by(Review.rating)
    ).all()
    breakdown = {str(star): 0 for star in (5, 4, 3, 2, 1)}
    for rating, count in breakdown_rows:
        breakdown[str(rating)] = int(count)

    average = db.scalar(
        select(func.avg(Review.rating)).where(
            Review.subject_id == user_id, Review.is_hidden.is_(False)
        )
    )

    return ReviewPage(
        items=[_review_out(review) for review in rows],
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
        average=round(float(average or 0.0), 2),
        breakdown=breakdown,
    )


def list_my_received_reviews(
    db: Session, viewer: User, *, page: int = 1, limit: int = 20
) -> ReviewPage:
    return list_user_reviews(db, viewer.id, page=page, limit=limit)


def list_pending_reviews(db: Session, viewer: User, *, limit: int = 20) -> PendingReviewListOut:
    """Completed trips this member still has to rate (either side)."""

    trips = db.scalars(
        select(Trip)
        .options(joinedload(Trip.ride), joinedload(Trip.driver), joinedload(Trip.passenger))
        .where(
            Trip.status == TripStatus.COMPLETED,
            (Trip.driver_id == viewer.id) | (Trip.passenger_id == viewer.id),
        )
        .order_by(Trip.completed_at.desc().nullslast(), Trip.created_at.desc())
        .limit(50)
    ).all()

    items: list[PendingReviewOut] = []
    for trip in trips:
        is_driver = trip.driver_id == viewer.id
        if trip.driver_reviewed_passenger if is_driver else trip.passenger_reviewed_driver:
            continue
        ride = trip.ride
        items.append(
            PendingReviewOut(
                trip_id=trip.id,
                counterpart=_author_out(trip.passenger if is_driver else trip.driver),
                direction=ride.direction if ride else None,
                pickup_area=ride.pickup_area if ride else None,
                destination_area=ride.destination_area if ride else None,
                departure_at=ride.departure_at if ride else None,
                completed_at=trip.completed_at,
                my_role="DRIVER" if is_driver else "PASSENGER",
            )
        )
        if len(items) >= limit:
            break

    return PendingReviewListOut(items=items, count=len(items))


# ----------------------------------------------------------------- moderation
def set_review_hidden(db: Session, review_id: uuid.UUID, hidden: bool) -> Review:
    """Hide or restore a review and rebuild the subject's aggregate.

    Called by the admin API, which owns the audit row and the commit.
    """

    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("This review could not be found.")
    if review.is_hidden == hidden:
        raise ConflictError(
            "This review is already hidden." if hidden else "This review is already visible."
        )
    review.is_hidden = hidden
    db.flush()
    recompute_rating(db, review.subject_id)
    return review
