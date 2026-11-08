"""Initial administrator provisioning (§17).

Rules implemented here:

1. Runs only when `ADMIN_BOOTSTRAP_ENABLED=true`.
2. Creates the admin **only if** no user with `ADMIN_EMAIL` exists.
3. Never resets or overwrites an existing admin password on restart.
4. The password is Argon2-hashed before it ever touches PostgreSQL.
5. The plaintext password is never logged.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import AccountStatus, UserRole, VerificationStatus
from app.models.user import User

logger = logging.getLogger("ssuet.rideshare.bootstrap")


def bootstrap_admin(db: Session) -> User | None:
    if not settings.ADMIN_BOOTSTRAP_ENABLED:
        logger.info("Admin bootstrap disabled (ADMIN_BOOTSTRAP_ENABLED=false).")
        return None

    email = settings.ADMIN_EMAIL.strip().lower()
    if not email or not settings.ADMIN_PASSWORD:
        logger.warning("Admin bootstrap skipped: ADMIN_EMAIL/ADMIN_PASSWORD not configured.")
        return None

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        logger.info("Admin bootstrap skipped: account %s already exists (password untouched).", email)
        return existing

    admin = User(
        email=email,
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        phone=_bootstrap_phone(db),
        full_name=settings.ADMIN_NAME.strip() or "System Administrator",
        role=UserRole.ADMIN,
        department="University Administration",
        university_id="SSUET-ADMIN-0001",
        is_university_email=True,
        verification_status=VerificationStatus.VERIFIED,
        account_status=AccountStatus.ACTIVE,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Bootstrap admin created: %s (id=%s). Set ADMIN_BOOTSTRAP_ENABLED=false now.", email, admin.id)
    return admin


def _bootstrap_phone(db: Session) -> str:
    """`users.phone` is unique; pick a free placeholder in a reserved range."""
    base = "+920000000000"
    candidate = base
    suffix = 0
    while db.scalar(select(User.id).where(User.phone == candidate)) is not None:
        suffix += 1
        candidate = f"+9200000{suffix:05d}"
    return candidate
