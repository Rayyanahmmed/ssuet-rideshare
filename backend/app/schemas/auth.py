"""Authentication contracts (§4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import UserRole
from app.schemas.user import UserMeOut


def _validate_password_strength(value: str) -> str:
    """Friendly, explicit rules instead of a single cryptic regex (§21)."""
    if len(value) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long.")
    if not any(c.isalpha() for c in value):
        raise ValueError("Password must contain at least one letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one number.")
    if value.lower() in {"password1", "passw0rd1", "12345678", "qwerty123"}:
        raise ValueError("This password is too common. Please choose another one.")
    return value


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
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
    password: str = Field(min_length=1, max_length=64)


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
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password_strength(value)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=20)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password_strength(value)


class SessionOut(BaseModel):
    """Developer-facing description of what a login returns."""

    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
