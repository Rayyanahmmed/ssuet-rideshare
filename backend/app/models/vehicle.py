"""Vehicle registration and admin verification (§5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import VehicleStatus, VehicleType

if TYPE_CHECKING:
    from app.models.ride import Ride
    from app.models.user import User


class Vehicle(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("passenger_capacity >= 1 AND passenger_capacity <= 8", name="capacity_range"),
        Index("ix_vehicles_owner_status", "owner_id", "status"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_column(VehicleType, 16), nullable=False)
    make_and_model: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str] = mapped_column(String(60), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Legacy external links (§5) — kept so an existing member's vehicle keeps working.
    vehicle_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Phase 10: uploaded files, readable by the owner and by reviewing administrators.
    photo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    registration_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    passenger_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)

    status: Mapped[VehicleStatus] = mapped_column(
        enum_column(VehicleStatus, 16), nullable=False, default=VehicleStatus.PENDING, index=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="vehicles", foreign_keys=[owner_id])
    rides: Mapped[list["Ride"]] = relationship(back_populates="vehicle")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vehicle {self.make_and_model} {self.registration_number}>"
