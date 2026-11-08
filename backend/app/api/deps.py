"""Authentication & authorization dependencies (§19, §22).

**The backend never trusts the client.** A JWT proves *who* the caller is; every
ownership, role and verification decision is re-derived here from the database.
"""

from __future__ import annotations

import uuid
from datetime import timezone
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import AccountStatus, UserRole, VerificationStatus
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token from /auth/login")

DbSession = Annotated[Session, Depends(get_db)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def _load_user_from_token(db: Session, credentials: HTTPAuthorizationCredentials | None) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Please log in to continue.")
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise UnauthorizedError("Your session has expired. Please log in again.") from None

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise UnauthorizedError("Your session is invalid. Please log in again.") from None

    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise UnauthorizedError("This account no longer exists.")
    revoked_at = user.sessions_revoked_at
    if revoked_at is not None:
        if revoked_at.tzinfo is None:  # SQLite returns naive datetimes
            revoked_at = revoked_at.replace(tzinfo=timezone.utc)
        issued_ms = int(payload.get("iat_ms") or int(payload.get("iat") or 0) * 1000)
        if issued_ms < int(revoked_at.timestamp() * 1000):
            raise UnauthorizedError("Your session has ended. Please log in again.")
    if user.account_status is AccountStatus.SUSPENDED:
        raise ForbiddenError(
            user.suspension_reason or "Your account is suspended.",
            details={"reason_code": "ACCOUNT_SUSPENDED"},
        )
    if user.account_status is AccountStatus.DEACTIVATED:
        raise ForbiddenError("This account has been deactivated.")
    return user


def get_current_user(db: DbSession, credentials: Credentials) -> User:
    """Any active, signed-in user (verified or not)."""
    return _load_user_from_token(db, credentials)


def get_optional_user(db: DbSession, credentials: Credentials) -> User | None:
    """For endpoints that behave differently when signed in (e.g. ride details)."""
    if credentials is None:
        return None
    return _load_user_from_token(db, credentials)


def require_verified_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Publishing rides, requesting seats and chatting require a verified account."""
    if current_user.verification_status is not VerificationStatus.VERIFIED:
        raise ForbiddenError(
            "Your university account is not verified yet. Submit your ID from your profile — "
            "an administrator reviews it, usually within one working day.",
            details={"reason_code": "ACCOUNT_NOT_VERIFIED"},
        )
    return current_user


def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role is not UserRole.ADMIN:
        raise ForbiddenError("Administrator access required.")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(require_verified_user)]
AdminUser = Annotated[User, Depends(require_admin)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
