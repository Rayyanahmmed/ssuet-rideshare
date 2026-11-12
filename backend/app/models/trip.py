"""Confirmed trip — created when a driver accepts exactly one request (§9, §10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import TripStatus

if TYPE_CHECKING:
    from app.models.chat import Conversation
    from app.models.review import Review
    from app.models.ride import Ride, RideRequest
    from app.models.user import User


class Trip(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One driver + one passenger + one ride.

    CONCURRENCY GUARD (§9): the database — not the application — guarantees that
    a ride can never have two live trips. `uq_trips_one_active_per_ride` is a
    partial unique index on `ride_id` that ignores CANCELLED trips, so a second
    `INSERT`/status-flip racing on the same ride fails with an IntegrityError.
    The seat reservation service additionally locks the ride row
    (`SELECT ... FOR UPDATE`) before accepting a request.
    """

    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_trips_request_id"),
        CheckConstraint("driver_id <> passenger_id", name="no_self_trip"),
        Index(
            "uq_trips_one_active_per_ride",
            "ride_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
            sqlite_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_trips_driver_status", "driver_id", "status"),
        Index("ix_trips_passenger_status", "passenger_id", "status"),
        Index("ix_trips_status_created", "status", "created_at"),
    )

    ride_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ride_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passenger_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TripStatus] = mapped_column(
        enum_column(TripStatus, 16), nullable=False, default=TripStatus.CONFIRMED, index=True
    )

    # --- precise meeting details: only shared with matched participants (§8) ---
    meeting_point: Mapped[str | None] = mapped_column(String(300), nullable=True)
    meeting_latitude: Mapped[float | None] = mapped_column(nullable=True)
    meeting_longitude: Mapped[float | None] = mapped_column(nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the driver marked "I have arrived" at the meeting point.
    driver_arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- per-side completion acknowledgement (both must confirm to finish) ---
    driver_confirmed_complete: Mapped[bool] = mapped_column(default=False, nullable=False)
    passenger_confirmed_complete: Mapped[bool] = mapped_column(default=False, nullable=False)

    # --- reviews given by each side of this trip (max one each) ---
    driver_reviewed_passenger: Mapped[bool] = mapped_column(default=False, nullable=False)
    passenger_reviewed_driver: Mapped[bool] = mapped_column(default=False, nullable=False)

    ride: Mapped["Ride"] = relationship(back_populates="trips", foreign_keys=[ride_id])
    request: Mapped["RideRequest"] = relationship(back_populates="trip", foreign_keys=[request_id])
    driver: Mapped["User"] = relationship(back_populates="trips_as_driver", foreign_keys=[driver_id])
    passenger: Mapped["User"] = relationship(
        back_populates="trips_as_passenger", foreign_keys=[passenger_id]
    )
    conversation: Mapped["Conversation | None"] = relationship(
        back_populates="trip", uselist=False, cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(back_populates="trip", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        return self.status in (TripStatus.CONFIRMED, TripStatus.IN_PROGRESS)

    def involves(self, user_id: uuid.UUID) -> bool:
        return user_id in (self.driver_id, self.passenger_id)
