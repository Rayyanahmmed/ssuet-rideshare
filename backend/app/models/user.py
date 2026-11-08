"""User identity, role profiles, auth tokens and blocking (§4, §5, §15)."""

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import AccountStatus, UserRole, VerificationStatus

API_PREFIX = settings.API_V1_PREFIX

if TYPE_CHECKING:
    from app.models.chat import Conversation, Message
    from app.models.notification import DeviceToken, Notification
    from app.models.report import Report
    from app.models.review import Review
    from app.models.ride import Ride, RideRequest
    from app.models.trip import Trip
    from app.models.vehicle import Vehicle
    from app.models.verification import Verification


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Every student, teacher and administrator."""

    __tablename__ = "users"
    # --- credentials ---
    email: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)

    # --- profile ---
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # Legacy external link (Phase 1–12). Still returned if nothing was uploaded, so no
    # member is forced to re-enter their profile after the Phase 13 change.
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Phase 13: the uploaded photo wins. Addressed by *user*, not by asset id, because a
    # profile picture is visible to every signed-in member while /media/{id} stays
    # owner+admin only.
    profile_photo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # `use_alter` because users → media_assets → users is a cycle: without it
        # SQLAlchemy cannot order CREATE/DROP statements and warns on every run.
        ForeignKey("media_assets.id", ondelete="SET NULL", use_alter=True,
                   name="fk_users_profile_photo_asset_id_media_assets"),
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, 16), nullable=False, default=UserRole.STUDENT)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    university_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_university_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- trust / moderation ---
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, 16), nullable=False, default=VerificationStatus.UNVERIFIED, index=True
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        enum_column(AccountStatus, 16), nullable=False, default=AccountStatus.ACTIVE, index=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- aggregate stats (denormalised for fast profile rendering) ---
    rating_average: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_trips_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when every session is ended (password reset/change, refresh-token theft). Access
    # tokens issued before this moment are refused at once, not after their 30-minute expiry.
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- relationships ---
    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    teacher_profile: Mapped["TeacherProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="owner", foreign_keys="Vehicle.owner_id"
    )
    rides: Mapped[list["Ride"]] = relationship(back_populates="driver", foreign_keys="Ride.driver_id")
    ride_requests: Mapped[list["RideRequest"]] = relationship(
        back_populates="passenger", foreign_keys="RideRequest.passenger_id"
    )
    trips_as_driver: Mapped[list["Trip"]] = relationship(
        back_populates="driver", foreign_keys="Trip.driver_id"
    )
    trips_as_passenger: Mapped[list["Trip"]] = relationship(
        back_populates="passenger", foreign_keys="Trip.passenger_id"
    )
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    device_tokens: Mapped[list["DeviceToken"]] = relationship(back_populates="user")
    reviews_written: Mapped[list["Review"]] = relationship(
        back_populates="author", foreign_keys="Review.author_id"
    )
    reviews_received: Mapped[list["Review"]] = relationship(
        back_populates="subject", foreign_keys="Review.subject_id"
    )
    reports_filed: Mapped[list["Report"]] = relationship(
        back_populates="reporter", foreign_keys="Report.reporter_id"
    )
    verifications: Mapped[list["Verification"]] = relationship(
        back_populates="user", foreign_keys="Verification.user_id"
    )

    __table_args__ = (
        CheckConstraint("length(full_name) >= 3", name="full_name_min_length"),
        CheckConstraint("rating_average >= 0 AND rating_average <= 5", name="rating_range"),
        UniqueConstraint("role", "university_id", name="uq_users_role_university_id"),
        Index("ix_users_role_status", "role", "account_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.full_name} ({self.role.value})>"

    # --------------------------------------------------------------- photos
    @property
    def photo_url(self) -> str | None:
        """The URL clients should load for this member's picture.

        An uploaded photo is served through `GET /users/{id}/photo`, which any
        authenticated member may read. Without one, the legacy external link (if the
        member ever set one) is returned unchanged.
        """
        if self.profile_photo_asset_id is not None:
            # The asset id in the query string *is* the cache key: a new upload changes
            # the URL, so clients and the CDN can cache avatars for an hour safely.
            return f"{API_PREFIX}/users/{self.id}/photo?v={self.profile_photo_asset_id}"
        return self.profile_photo_url


class StudentProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    student_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    degree_programme: Mapped[str | None] = mapped_column(String(120), nullable=True)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_area: Mapped[str | None] = mapped_column(String(160), nullable=True)

    user: Mapped["User"] = relationship(back_populates="student_profile")


class TeacherProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "teacher_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    employee_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    designation: Mapped[str] = mapped_column(String(120), nullable=False)
    home_area: Mapped[str | None] = mapped_column(String(160), nullable=True)

    user: Mapped["User"] = relationship(back_populates="teacher_profile")


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Refresh tokens are stored hashed and rotated on every use (§4, §22)."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_revoked", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PasswordResetToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerificationToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Single-use token proving control of an email address (§4).

    Only the SHA-256 hash is stored, so a database leak cannot be replayed.
    """

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserBlock(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user can block another user; the blocked pair cannot match again (§15)."""

    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
        CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
    )

    blocker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
