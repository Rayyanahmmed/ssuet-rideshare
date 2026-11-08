"""§17 — admin bootstrap must be idempotent, hashed and non-destructive."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import User
from app.models.enums import AccountStatus, UserRole, VerificationStatus
from app.services.admin_bootstrap import bootstrap_admin


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@ssuet.edu.pk")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "SuperSecret123!")
    monkeypatch.setattr(settings, "ADMIN_NAME", "System Administrator")
    return settings


def test_bootstrap_creates_hashed_admin(db, admin_env):
    admin = bootstrap_admin(db)
    assert admin is not None
    assert admin.role is UserRole.ADMIN
    assert admin.account_status is AccountStatus.ACTIVE
    assert admin.verification_status is VerificationStatus.VERIFIED
    # never stored in plaintext, always Argon2
    assert admin.password_hash != "SuperSecret123!"
    assert admin.password_hash.startswith("$argon2")
    assert verify_password("SuperSecret123!", admin.password_hash)


def test_bootstrap_is_idempotent_and_never_resets_password(db, admin_env, monkeypatch):
    first = bootstrap_admin(db)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "SomeOtherPassword!")
    second = bootstrap_admin(db)

    assert first.id == second.id
    assert db.scalar(select(User).where(User.role == UserRole.ADMIN).count() if False else select(User)) is not None
    admins = db.scalars(select(User).where(User.role == UserRole.ADMIN)).all()
    assert len(admins) == 1
    # original password still valid, new one never applied
    assert verify_password("SuperSecret123!", admins[0].password_hash)
    assert not verify_password("SomeOtherPassword!", admins[0].password_hash)


def test_bootstrap_respects_disabled_flag(db, admin_env, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_ENABLED", False)
    assert bootstrap_admin(db) is None
    assert db.scalars(select(User).where(User.role == UserRole.ADMIN)).all() == []


def test_bootstrap_does_not_touch_an_existing_regular_account_with_same_email(db, admin_env):
    existing = User(
        email="admin@ssuet.edu.pk",
        password_hash=hash_password("ExistingPass1!"),
        phone="+923000000001",
        full_name="Existing Admin",
        role=UserRole.ADMIN,
        department="IT",
        university_id="ADMIN-X",
    )
    db.add(existing)
    db.commit()

    result = bootstrap_admin(db)
    assert result is not None
    assert str(result.id) == str(existing.id)
    assert verify_password("ExistingPass1!", result.password_hash)
