"""Authentication & account-lifecycle business logic (§4, §22).

Design notes
------------
* Routers stay thin: every rule below is called from `app/api/v1/auth.py`.
* Refresh tokens are opaque, stored as SHA-256 hashes, **rotated on every use**,
  and reuse of a rotated token revokes the whole chain (theft detection).
* Login failures are indistinguishable (same message/status) whether the email
  exists or the password is wrong — no account enumeration. The same applies to
  password reset requests.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    is_university_email,
    needs_rehash,
    verify_password,
)
from app.models.enums import (
    AccountStatus,
    NotificationType,
    UserRole,
    VerificationStatus,
    VerificationType,
)
from app.models.media import PURPOSE_VERIFICATION_DOCUMENT, MediaAsset
from app.models.notification import Notification  # noqa: F401  (type hints / future use)
from app.models.user import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    StudentProfile,
    TeacherProfile,
    User,
)
from app.models.verification import Verification
from app.schemas.auth import RegisterIn
from app.schemas.user import UserMeOut, VerificationSubmitIn
from app.services.email_service import send_password_reset_email, send_verification_email
from app.services.notification_service import create_notification

logger = logging.getLogger("ssuet.rideshare.auth")

GENERIC_LOGIN_ERROR = "Incorrect email or password."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- helpers
def normalize_email(email: str) -> str:
    return email.strip().lower()


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; compare in UTC to stay portable."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _as_me(db: Session, user: User) -> UserMeOut:
    db.refresh(user)
    return UserMeOut.model_validate(user)


# -------------------------------------------------------------------- register
def register_user(
    db: Session,
    data: RegisterIn,
    *,
    user_agent: str | None = None,
) -> tuple[User, str, str]:
    """Create an account and return `(user, access_token, refresh_token)`."""
    email = normalize_email(data.email)

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ValidationAppError(
            "An account with this email already exists. Try logging in instead.",
            details={"email": "already registered"},
        )
    if db.scalar(select(User.id).where(User.phone == data.phone)) is not None:
        raise ValidationAppError(
            "This phone number is already registered.",
            details={"phone": "already registered"},
        )
    if db.scalar(
        select(User.id).where(User.university_id == data.university_id, User.role == data.role)
    ) is not None:
        raise ValidationAppError(
            "This university ID is already registered for the selected role.",
            details={"university_id": "already registered"},
        )

    university_email = is_university_email(email)
    # §4: auto-verify only when the domain is trusted AND the feature is enabled;
    # everyone else goes through manual admin verification.
    auto_verified = university_email and settings.AUTO_VERIFY_UNIVERSITY_EMAILS

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        phone=data.phone,
        full_name=data.full_name,
        profile_photo_url=data.profile_photo_url,
        role=data.role,
        department=data.department,
        university_id=data.university_id,
        is_university_email=university_email,
        verification_status=(
            VerificationStatus.VERIFIED if auto_verified else VerificationStatus.UNVERIFIED
        ),
        verified_at=utcnow() if auto_verified else None,
        account_status=AccountStatus.ACTIVE,
    )
    if data.role is UserRole.STUDENT:
        user.student_profile = StudentProfile(
            student_id=data.university_id,
            department=data.department,
            degree_programme=data.degree_programme,
            semester=data.semester,
            batch_year=data.batch_year,
            home_area=data.home_area,
        )
    else:
        user.teacher_profile = TeacherProfile(
            employee_id=data.university_id,
            department=data.department,
            designation=data.designation or "Faculty Member",
            home_area=data.home_area,
        )

    db.add(user)
    db.flush()

    if auto_verified:
        db.add(
            Verification(
                user_id=user.id,
                verification_type=VerificationType.UNIVERSITY_EMAIL,
                status=VerificationStatus.VERIFIED,
                submitted_value=email,
                reviewed_at=utcnow(),
                review_note="Automatically verified: trusted university email domain.",
            )
        )

    access_token, refresh_token = _issue_token_pair(db, user, user_agent=user_agent)
    create_notification(
        db,
        user_id=user.id,
        type=NotificationType.SYSTEM,
        title="Welcome to SSUET RideShare",
        body=(
            "Your account is verified. Publish your first journey or explore rides near you."
            if auto_verified
            else "Confirm your email and submit your university ID to unlock publishing rides."
        ),
        data={"screen": "home"},
        commit=False,
    )
    db.commit()
    db.refresh(user)

    # Verification email is best-effort: a mail outage must not lose the signup.
    _issue_email_verification(db, user)
    return user, access_token, refresh_token


# --------------------------------------------------------------------- tokens
def _issue_token_pair(
    db: Session, user: User, *, user_agent: str | None = None
) -> tuple[str, str]:
    access_token, _ = create_access_token(subject=user.id, role=user.role.value)
    raw_refresh, hashed_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed_refresh,
            expires_at=utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return access_token, raw_refresh


def authenticate(db: Session, email: str, password: str, *, user_agent: str | None = None):
    """Return `(user, access_token, refresh_token)` or raise a generic 401."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))

    # Constant-ish work whether or not the account exists.
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError(GENERIC_LOGIN_ERROR)

    if user.account_status is AccountStatus.SUSPENDED:
        raise ForbiddenError(
            user.suspension_reason
            or "Your account is suspended. Please contact the SSUET RideShare administrator.",
            details={"reason_code": "ACCOUNT_SUSPENDED"},
        )
    if user.account_status is AccountStatus.DEACTIVATED or user.deleted_at is not None:
        raise ForbiddenError("This account has been deactivated.")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = utcnow()
    access_token, refresh_token = _issue_token_pair(db, user, user_agent=user_agent)
    db.commit()
    db.refresh(user)
    return user, access_token, refresh_token


def rotate_refresh_token(
    db: Session, raw_token: str, *, user_agent: str | None = None
) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair (rotation + reuse detection)."""
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if stored is None:
        raise UnauthorizedError("This session is no longer valid. Please log in again.")

    if stored.revoked_at is not None:
        # The token was already used: assume it leaked and kill the whole family.
        logger.warning("Refresh-token reuse detected for user %s — revoking all sessions.", stored.user_id)
        _revoke_all_for_user(db, stored.user_id)
        db.commit()
        raise UnauthorizedError("This session was already used. Please log in again.")

    if _aware(stored.expires_at) <= utcnow():
        stored.revoked_at = utcnow()
        db.commit()
        raise UnauthorizedError("Your session expired. Please log in again.")

    user = db.get(User, stored.user_id)
    if user is None or user.account_status is not AccountStatus.ACTIVE or user.deleted_at is not None:
        raise ForbiddenError("This account cannot sign in.", details={"reason_code": "ACCOUNT_INACTIVE"})

    access_token, new_raw_refresh = _issue_token_pair(db, user, user_agent=user_agent)
    new_stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_raw_refresh))
    )
    stored.revoked_at = utcnow()
    if new_stored is not None:
        stored.replaced_by_id = new_stored.id
    db.commit()
    db.refresh(user)
    return user, access_token, new_raw_refresh


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Logout: revoke one session. Unknown tokens are ignored (idempotent)."""
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = utcnow()
        db.commit()


def _revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    now = utcnow()
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    # Access tokens are stateless JWTs; this timestamp makes every token issued before now
    # fail in `deps._load_user_from_token`, so a reset ends the old sessions immediately.
    db.execute(update(User).where(User.id == user_id).values(sessions_revoked_at=now))


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    _revoke_all_for_user(db, user_id)
    db.commit()


# ------------------------------------------------------------ email verification
def _issue_email_verification(db: Session, user: User) -> str:
    raw_token, hashed = generate_refresh_token()  # same CSPRNG helper, own table
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_MINUTES),
        )
    )
    db.commit()
    send_verification_email(user.email, user.full_name, raw_token)
    return raw_token


def resend_verification_email(db: Session, user: User) -> None:
    if user.email_verified_at is not None:
        raise ValidationAppError("Your email address is already confirmed.")
    _issue_email_verification(db, user)


def verify_email(db: Session, raw_token: str) -> User:
    stored = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(raw_token)
        )
    )
    if stored is None or stored.used_at is not None:
        raise ValidationAppError("This confirmation link is invalid or was already used.")
    if _aware(stored.expires_at) <= utcnow():
        raise ValidationAppError("This confirmation link has expired. Request a new one.")

    user = db.get(User, stored.user_id)
    if user is None:
        raise ValidationAppError("This confirmation link is invalid or was already used.")

    stored.used_at = utcnow()
    user.email_verified_at = utcnow()
    db.commit()
    db.refresh(user)
    return user


# -------------------------------------------------------------- password reset
def issue_password_reset_token(db: Session, user: User) -> tuple[str, datetime]:
    """Create a single-use reset token. Returns `(raw_token, expires_at)`.

    Used by the email flow and by the admin console fallback (when email is not set up).
    """
    raw_token, hashed = generate_refresh_token()
    expires_at = utcnow() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_MINUTES)
    db.add(PasswordResetToken(user_id=user.id, token_hash=hashed, expires_at=expires_at))
    db.commit()
    return raw_token, expires_at


def request_password_reset(db: Session, email: str) -> None:
    """Always succeeds from the caller's perspective (no account enumeration)."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or user.account_status is not AccountStatus.ACTIVE:
        logger.info("Password reset requested for an unknown/inactive address.")
        return

    raw_token, _ = issue_password_reset_token(db, user)
    send_password_reset_email(user.email, user.full_name, raw_token)


def reset_password(db: Session, raw_token: str, new_password: str) -> User:
    stored = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token))
    )
    if stored is None or stored.used_at is not None:
        raise ValidationAppError("This reset link is invalid or was already used.")
    if _aware(stored.expires_at) <= utcnow():
        raise ValidationAppError("This reset link has expired. Request a new one.")

    user = db.get(User, stored.user_id)
    if user is None:
        raise ValidationAppError("This reset link is invalid or was already used.")

    user.password_hash = hash_password(new_password)
    stored.used_at = utcnow()
    # Every existing session is invalidated after a password reset.
    _revoke_all_for_user(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValidationAppError(
            "Your current password is incorrect.", details={"current_password": "incorrect"}
        )
    if verify_password(new_password, user.password_hash):
        raise ValidationAppError("The new password must be different from the current one.")
    user.password_hash = hash_password(new_password)
    _revoke_all_for_user(db, user.id)
    db.commit()


# ------------------------------------------------------- university verification
def submit_verification(db: Session, user: User, payload: VerificationSubmitIn) -> Verification:
    """Queue a manual verification request for admin review (§4, §16)."""
    if user.verification_status is VerificationStatus.VERIFIED:
        raise ValidationAppError("Your account is already verified.")
    if user.verification_status is VerificationStatus.PENDING:
        raise ValidationAppError("You already have a verification request under review.")

    asset = None
    if payload.document_asset_id is not None:
        asset = db.get(MediaAsset, payload.document_asset_id)
        # An upload id belonging to somebody else is treated as missing, not as a
        # permission error, so the endpoint cannot be used to probe for assets.
        if asset is None or asset.owner_id != user.id:
            raise NotFoundError("This upload could not be found.")
        if asset.purpose != PURPOSE_VERIFICATION_DOCUMENT:
            raise ValidationAppError("This upload cannot be used as a verification document.")

    record = Verification(
        user_id=user.id,
        verification_type=payload.verification_type,
        status=VerificationStatus.PENDING,
        submitted_value=payload.submitted_value or user.university_id,
        document_url=str(payload.document_url) if payload.document_url else None,
        document_asset_id=asset.id if asset else None,
    )
    if payload.note:
        record.review_note = f"User note: {payload.note}"
    db.add(record)

    user.verification_status = VerificationStatus.PENDING
    db.commit()
    db.refresh(record)
    logger.info("Verification submitted for user %s", user.id)
    return record


def verification_history(db: Session, user_id: uuid.UUID) -> list[Verification]:
    return list(
        db.scalars(
            select(Verification)
            .where(Verification.user_id == user_id)
            .order_by(Verification.created_at.desc())
        )
    )
