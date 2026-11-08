"""Ratings & reviews (§14)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.trip import Trip
    from app.models.user import User


class Review(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One review per author per trip; only trip participants may review."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("trip_id", "author_id", name="uq_reviews_trip_author"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
        CheckConstraint("author_id <> subject_id", name="no_self_review"),
        Index("ix_reviews_subject_created", "subject_id", "created_at"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(default=False, nullable=False)

    trip: Mapped["Trip"] = relationship(back_populates="reviews", foreign_keys=[trip_id])
    author: Mapped["User"] = relationship(back_populates="reviews_written", foreign_keys=[author_id])
    subject: Mapped["User"] = relationship(back_populates="reviews_received", foreign_keys=[subject_id])
