"""Safety reports / complaints (§15)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import ReportCategory, ReportStatus

if TYPE_CHECKING:
    from app.models.admin_action import AdminAction
    from app.models.media import MediaAsset
    from app.models.ride import Ride
    from app.models.trip import Trip
    from app.models.user import User


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("reporter_id <> reported_user_id", name="no_self_report"),
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_reported_user", "reported_user_id", "status"),
    )

    reporter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reported_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rides.id", ondelete="SET NULL"), nullable=True
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[ReportCategory] = mapped_column(enum_column(ReportCategory, 32), nullable=False)
    # Phase 15: a report about a picture pins the exact asset that was reported. If the
    # member uploads a new photo, the old file is kept so the office can still see what
    # was complained about — evidence must not disappear because the report was acted on.
    reported_photo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "media_assets.id",
            ondelete="SET NULL",
            name="fk_reports_reported_photo_asset_id_media_assets",
        ),
        nullable=True,
    )
    photo_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        enum_column(ReportStatus, 16), nullable=False, default=ReportStatus.OPEN, index=True
    )

    handled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reporter: Mapped["User"] = relationship(back_populates="reports_filed", foreign_keys=[reporter_id])
    reported_user: Mapped["User"] = relationship(foreign_keys=[reported_user_id])
    ride: Mapped["Ride | None"] = relationship(foreign_keys=[ride_id])
    trip: Mapped["Trip | None"] = relationship(foreign_keys=[trip_id])
    admin_actions: Mapped[list["AdminAction"]] = relationship(back_populates="report")
    reported_photo: Mapped["MediaAsset | None"] = relationship(foreign_keys=[reported_photo_asset_id])
