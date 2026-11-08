"""User / profile request & response contracts (§5).

Two deliberately different shapes:

* `UserMeOut`    — the owner (and admins) see email, phone, university id.
* `UserPublicOut` — what other members of the community may see: no email, no
  phone, no university id, no exact home area. Privacy is enforced by the schema,
  not by remembering to strip fields in a view (§8, §15, §22).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models.enums import (
    AccountStatus,
    UserRole,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
    VerificationType,
)
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- profiles


class StudentProfileOut(ORMModel):
    student_id: str
    department: str
    degree_programme: str | None = None
    semester: int | None = None
    batch_year: int | None = None
    home_area: str | None = None


class TeacherProfileOut(ORMModel):
    employee_id: str
    department: str
    designation: str
    home_area: str | None = None


class VehicleOut(ORMModel):
    id: uuid.UUID
    vehicle_type: VehicleType
    make_and_model: str
    color: str
    passenger_capacity: int
    vehicle_photo_url: str | None = None
    status: VehicleStatus
    # registration_number intentionally omitted from public payloads


# ------------------------------------------------------------- me / public


class UserMeOut(ORMModel):
    """Owner view of the account."""

    id: uuid.UUID
    email: str
    phone: str
    full_name: str
    # Derived from `User.photo_url`: an uploaded picture wins, the legacy external link
    # is the fallback (Phase 13). The URL carries the asset id as a cache key.
    profile_photo_url: str | None = Field(default=None, validation_alias="photo_url")
    role: UserRole
    department: str
    university_id: str
    is_university_email: bool
    verification_status: VerificationStatus
    account_status: AccountStatus
    suspension_reason: str | None = None
    email_verified_at: datetime | None = None
    verified_at: datetime | None = None
    rating_average: float
    rating_count: int
    completed_trips_count: int
    created_at: datetime
    student_profile: StudentProfileOut | None = None
    teacher_profile: TeacherProfileOut | None = None


class UserPublicOut(ORMModel):
    """Public profile — what a stranger is allowed to know before matching."""

    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = Field(default=None, validation_alias="photo_url")
    role: UserRole
    department: str
    verification_status: VerificationStatus
    rating_average: float
    rating_count: int
    completed_trips_count: int
    created_at: datetime


class UserUpdateIn(BaseModel):
    """Partial profile update. Empty strings are rejected rather than stored."""

    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    # Legacy: an external link. Phase 13 clients upload instead — see
    # POST /users/me/photo, which takes precedence over anything set here.
    profile_photo_url: HttpUrl | None = Field(
        default=None, deprecated=True, description="Deprecated: use POST /users/me/photo"
    )
    department: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, min_length=10, max_length=20)
    home_area: str | None = Field(default=None, max_length=160)
    degree_programme: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    batch_year: int | None = Field(default=None, ge=2000, le=2100)
    designation: str | None = Field(default=None, max_length=120)

    @field_validator("full_name", "department", "phone", "home_area")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value else value


class VerificationSubmitIn(BaseModel):
    """Manual university-verification submission (§4).

    Students upload their student card, teachers their employee card. Admins
    review the queue in the dashboard (Phase 6).
    """

    verification_type: VerificationType
    submitted_value: str | None = Field(
        default=None, max_length=180, description="Student ID / employee ID / university email"
    )
    # Two supported ways to supply the document. Upload first (POST /uploads/verification)
    # and pass the returned id — preferred, because the file stays inside the platform and
    # only its owner and an administrator can open it. An external https link is still
    # accepted for members who keep their card in Drive/OneDrive.
    document_asset_id: uuid.UUID | None = Field(
        default=None, description="id returned by POST /uploads/verification"
    )
    document_url: HttpUrl | None = Field(
        default=None, description="External https link to the document (alternative to an upload)"
    )
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _exactly_one_document(self) -> "VerificationSubmitIn":
        if bool(self.document_asset_id) == bool(self.document_url):
            raise ValueError(
                "Provide either document_asset_id (uploaded file) or document_url (link), not both."
            )
        return self


class VerificationOut(ORMModel):
    id: uuid.UUID
    verification_type: VerificationType
    status: VerificationStatus
    submitted_value: str | None = None
    document_url: str | None = None
    document_asset_id: uuid.UUID | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ReviewOut(ORMModel):
    id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime
    author: UserPublicOut
