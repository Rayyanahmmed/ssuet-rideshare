"""Rating & review contracts (§14).

A review is strictly tied to a **completed trip** and to the two people who took
part in it: one author, one subject, one row per trip and author (the database
enforces this with `uq_reviews_trip_author`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import RideDirection, UserRole

#: A comment is optional, but when present it must say something.
COMMENT_MIN = 3
COMMENT_MAX = 500


class ReviewAuthorOut(BaseModel):
    """Who wrote a review — a public-level summary, never contact details."""

    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    role: UserRole
    department: str


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5, description="1 = poor, 5 = excellent")
    comment: str | None = Field(default=None, max_length=COMMENT_MAX)

    @field_validator("comment")
    @classmethod
    def _clean_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            return None
        if len(cleaned) < COMMENT_MIN:
            raise ValueError("Write at least a few words, or leave the comment empty.")
        return cleaned


class ReviewOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    rating: int
    comment: str | None = None
    direction: RideDirection | None = None
    pickup_area: str | None = None
    destination_area: str | None = None
    author: ReviewAuthorOut
    subject_id: uuid.UUID
    created_at: datetime


class ReviewPage(BaseModel):
    """Reviews about one member, with the distribution the profile screen renders."""

    items: list[ReviewOut]
    total: int
    page: int
    limit: int
    pages: int
    average: float
    #: `{"5": 4, "4": 1, …}` — always contains all five keys.
    breakdown: dict[str, int]


class PendingReviewOut(BaseModel):
    """A finished trip this member still owes a rating for."""

    trip_id: uuid.UUID
    counterpart: ReviewAuthorOut
    direction: RideDirection | None = None
    pickup_area: str | None = None
    destination_area: str | None = None
    departure_at: datetime | None = None
    completed_at: datetime | None = None
    my_role: str


class PendingReviewListOut(BaseModel):
    items: list[PendingReviewOut]
    count: int
