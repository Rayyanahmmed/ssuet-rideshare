"""University verification requests (§4, §16)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import VerificationStatus, VerificationType

if TYPE_CHECKING:
    from app.models.user import User


class Verification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Audit trail of every verification attempt (email, ID card, manual)."""

    __tablename__ = "verifications"
    __table_args__ = (
        Index("ix_verifications_status_created", "status", "created_at"),
        Index("ix_verifications_user", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verification_type: Mapped[VerificationType] = mapped_column(
        enum_column(VerificationType, 32), nullable=False
    )
    status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, 16), nullable=False, default=VerificationStatus.PENDING
    )
    submitted_value: Mapped[str | None] = mapped_column(String(180), nullable=True)
    # Exactly one of the two is set: an external https link (legacy) or an uploaded
    # asset that is served through GET /media/{id}.
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="verifications", foreign_keys=[user_id])
