"""Uploaded media assets (§4, §16).

New files are stored in the database (`MediaAsset.blob`) and referenced by a UUID row,
never by their original filename. Rows written before that change keep their file on disk
under `settings.MEDIA_ROOT`; `media_service.read_bytes` serves both. The row is the authorisation anchor: a member may
read their own assets, an administrator may read any asset, nobody else can.

Phase 9 replaces the "paste a link to your ID photo" workaround with a real
multipart upload, so the verification queue is self-contained.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User

# Purpose values. Kept as a string column rather than a DB enum so adding a new
# upload kind (vehicle papers, profile photo) never needs a migration.
PURPOSE_VERIFICATION_DOCUMENT = "VERIFICATION_DOCUMENT"
PURPOSE_VEHICLE_DOCUMENT = "VEHICLE_DOCUMENT"
PURPOSE_PROFILE_PHOTO = "PROFILE_PHOTO"  # Phase 13 — visible to every member


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One stored file: verification ID card, employee card, or future upload."""

    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    # Path relative to MEDIA_ROOT — never absolute, so the root can move between
    # environments (and so a leaked row cannot be turned into an arbitrary read).
    storage_path: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The file bytes themselves (PostgreSQL bytea). Hosts without a persistent disk (free
    # tiers) lose local files on every restart, so new uploads live in the database.
    # `deferred` keeps list and count queries from loading megabytes of images.
    # NULL = legacy row written to disk under MEDIA_ROOT before this column existed.
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)

    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])
