"""Ratings & reviews — `/api/v1/reviews` (§14).

Reviews are how trust is built in a community where money never changes hands, so
the write path is tightly constrained: completed trips only, participants only,
one review per side. The read path is public to signed-in members because a rating
average is part of a member's reputation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.schemas.review import (
    PendingReviewListOut,
    ReviewIn,
    ReviewOut,
    ReviewPage,
)
from app.services import review_service

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.post(
    "/trips/{trip_id}",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Rate the other participant of a completed trip",
)
@limiter.limit("10/minute")
def create_review(
    trip_id: uuid.UUID,
    payload: ReviewIn,
    request: Request,  # required by the rate limiter
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewOut:
    return review_service.create_review(
        db,
        current_user,
        trip_id=trip_id,
        rating=payload.rating,
        comment=payload.comment,
    )


@router.get("/pending", response_model=PendingReviewListOut, summary="Finished trips awaiting my rating")
def pending_reviews(current_user: CurrentUser, db: DbSession) -> PendingReviewListOut:
    return review_service.list_pending_reviews(db, current_user)


@router.get("/me/received", response_model=ReviewPage, summary="Reviews I have received")
def my_received_reviews(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> ReviewPage:
    return review_service.list_my_received_reviews(db, current_user, page=page, limit=limit)


@router.get("/users/{user_id}", response_model=ReviewPage, summary="Reviews about a member")
def user_reviews(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> ReviewPage:
    return review_service.list_user_reviews(db, user_id, page=page, limit=limit)
