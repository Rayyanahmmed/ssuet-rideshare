"""Password hashing, JWT access tokens and opaque refresh-token helpers (§4, §22).

* Passwords: Argon2id (memory-hard, current OWASP recommendation).
* Access token: short-lived signed JWT.
* Refresh token: random 256-bit opaque string, stored **SHA-256 hashed** in the
  database so a database leak cannot be replayed. Rotated on every refresh.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import settings

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

TokenType = Literal["access"]


# ----------------------------- passwords -----------------------------
def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# ----------------------------- JWT ----------------------------------
def create_access_token(
    *, subject: str | uuid.UUID, role: str, extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        # Millisecond issue time: session revocation compares against it, so a token issued
        # in the same second as a password reset is still ended.
        "iat_ms": int(now.timestamp() * 1000),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), expire


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises `JWTError` for invalid/expired tokens — callers convert to HTTP 401."""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    return payload


# ------------------------- refresh tokens ---------------------------
def generate_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_for_client, sha256_hash_for_database)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)


# --------------------------- misc utils -----------------------------
def generate_otp(digits: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def is_university_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in settings.university_domains
