"""Authentication contracts (§4)."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator, model_validator

from app.core.config import settings
from app.models.enums import UserRole
from app.schemas.user import UserMeOut

# SSUET student roll number: batch year, F (Fall) or S (Spring), programme, roll number.
# Example: 2023F-Bcs-301
STUDENT_ID_PATTERN = re.compile(r"^(\d{4})([FS])-([A-Za-z]{2,6})-(\d{3})$", re.IGNORECASE)
STUDENT_ID_HELP = "Student ID must look like 2023F-Bcs-301 (batch year, F or S, programme, roll number)."


def normalize_student_id(value: str) -> str:
    """Return the canonical form (2023F-Bcs-301) or raise a friendly error."""
    match = STUDENT_ID_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(STUDENT_ID_HELP)
    year, season, programme, roll = match.groups()
    return f"{year}{season.upper()}-{programme.capitalize()}-{roll}"


PASSWORD_MAX_LENGTH = 128


def _validate_password_strength(value: str) -> str:
    """Passwords are user-chosen: any text is accepted, as long as it is not empty or absurdly long.

    Argon2 hashes any length, so the only limits are sanity bounds (not blank, at most 128 characters).
    """
    if len(value) < max(1, settings.PASSWORD_MIN_LENGTH):
        raise ValueError("Please enter a password.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters long.")
    return value


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=10, max_length=20, examples=["+923001234567"])
    role: UserRole = UserRole.STUDENT
    university_id: str = Field(min_length=3, max_length=40, examples=["SSUET-2022-101"])
    department: str = Field(min_length=2, max_length=120)
    profile_photo_url: str | None = Field(default=None, max_length=500)

    # student-only (optional)
    degree_programme: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    batch_year: int | None = Field(default=None, ge=2000, le=2100)
    # teacher-only (optional)
    designation: str | None = Field(default=None, max_length=120)

    home_area: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password_strength(value)

    @field_validator("full_name", "department", "university_id", "phone")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("university_id")
    @classmethod
    def _student_id_format(cls, value: str, info: ValidationInfo) -> str:
        """Students get a fixed roll-number format; teacher employee IDs stay free text."""
        if info.data.get("role", UserRole.STUDENT) is UserRole.STUDENT:
            return normalize_student_id(value)
        return value

    @field_validator("role")
    @classmethod
    def _no_self_service_admin(cls, value: UserRole) -> UserRole:
        """Nobody can register themselves as an administrator (§17)."""
        if value is UserRole.ADMIN:
            raise ValueError("Administrator accounts cannot be self-registered.")
        return value

    @model_validator(mode="after")
    def _role_specific_fields(self) -> "RegisterIn":
        if self.role is UserRole.TEACHER and self.semester is not None:
            raise ValueError("semester applies to students only.")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")
    user: UserMeOut


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutIn(BaseModel):
    refresh_token: str = Field(min_length=20)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=1, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password_strength(value)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=20)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password_strength(value)


class SessionOut(BaseModel):
    """Developer-facing description of what a login returns."""

    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
