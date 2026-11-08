"""Published journeys (rides) and join requests — the core of the platform (§7–§9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column, money_column
from app.models.enums import (
    ContributionType,
    FuelPreference,
    RideDirection,
    RideRequestStatus,
    RideStatus,
    VehicleType,
)

if TYPE_CHECKING:
    from app.models.trip import Trip
    from app.models.user import User
    from app.models.vehicle import Vehicle


class Ride(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A journey published by a driver.

    Privacy note (§8): `pickup_area` / `destination_area` are coarse, public
    labels. `pickup_latitude/longitude` are exact meeting coordinates and are
    only exposed to the matched passenger and to admins.
    """

    __tablename__ = "rides"
    __table_args__ = (
        CheckConstraint("available_seats >= 1 AND available_seats <= 8", name="seats_range"),
        CheckConstraint(
            "fuel_preference <> 'SHARE_FUEL' OR contribution_type <> 'NONE'",
            name="fuel_share_needs_contribution_type",
        ),
        CheckConstraint("contribution_amount IS NULL OR contribution_amount >= 0", name="contribution_non_negative"),
        Index("ix_rides_discovery", "status", "departure_date", "direction"),
        Index("ix_rides_driver_status", "driver_id", "status"),
        Index("ix_rides_departure", "departure_at"),
    )

    driver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_column(VehicleType, 16), nullable=False)
    direction: Mapped[RideDirection] = mapped_column(enum_column(RideDirection, 32), nullable=False)

    # --- locations ---
    pickup_area: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    pickup_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_area: Mapped[str] = mapped_column(String(160), nullable=False)
    destination_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # --- schedule ---
    departure_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # --- capacity (business rule: ONE confirmed passenger per ride in the MVP) ---
    available_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seats_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- fuel agreement (§7) — cash/offline only, never a platform payment ---
    fuel_preference: Mapped[FuelPreference] = mapped_column(
        enum_column(FuelPreference, 16), nullable=False, default=FuelPreference.FREE
    )
    contribution_type: Mapped[ContributionType] = mapped_column(
        enum_column(ContributionType, 16), nullable=False, default=ContributionType.NONE
    )
    contribution_amount: Mapped[float | None] = mapped_column(money_column(), nullable=True)
    contribution_note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RideStatus] = mapped_column(
        enum_column(RideStatus, 16), nullable=False, default=RideStatus.OPEN, index=True
    )

    # --- lifecycle timestamps ---
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin_cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- relationships ---
    driver: Mapped["User"] = relationship(back_populates="rides", foreign_keys=[driver_id])
    vehicle: Mapped["Vehicle | None"] = relationship(back_populates="rides")
    requests: Mapped[list["RideRequest"]] = relationship(
        back_populates="ride", cascade="all, delete-orphan"
    )
    # a ride may accumulate several trips only if earlier ones were cancelled
    trips: Mapped[list["Trip"]] = relationship(back_populates="ride", foreign_keys="Trip.ride_id")

    @property
    def active_trip(self) -> "Trip | None":
        """The single live trip, if the ride is currently matched."""
        for trip in self.trips:
            if trip.status != "CANCELLED":
                return trip
        return None

    # --- helpers mirroring the state machine in §10 ---
    @property
    def is_open(self) -> bool:
        return self.status == RideStatus.OPEN and self.seats_remaining > 0

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ride {self.pickup_area}->{self.destination_area} {self.status.value}>"


class RideRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A passenger's request to join a published ride."""

    __tablename__ = "ride_requests"
    __table_args__ = (
        # one passenger may hold only one *pending* request per ride
        Index(
            "uq_ride_requests_pending_pair",
            "ride_id",
            "passenger_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
        Index("ix_ride_requests_ride_status", "ride_id", "status"),
        Index("ix_ride_requests_passenger_status", "passenger_id", "status"),
    )

    ride_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    passenger_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[RideRequestStatus] = mapped_column(
        enum_column(RideRequestStatus, 16), nullable=False, default=RideRequestStatus.PENDING, index=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    ride: Mapped["Ride"] = relationship(back_populates="requests")
    passenger: Mapped["User"] = relationship(back_populates="ride_requests", foreign_keys=[passenger_id])
    trip: Mapped["Trip | None"] = relationship(back_populates="request", uselist=False)
