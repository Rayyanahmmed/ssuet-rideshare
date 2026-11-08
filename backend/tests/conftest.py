"""Pytest fixtures.

The environment is configured *before* the application is imported so that
`Settings` (a cached singleton) points at an isolated SQLite test database.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "ssuet_rideshare_test.db"

# CI runs the same suite twice: on SQLite (the local default) and against a
# PostgreSQL service, so a dialect difference cannot reach production unnoticed.
# Point TEST_DATABASE_URL at postgresql+psycopg://… to switch.
DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+pysqlite:///{TEST_DB}"

os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=DATABASE_URL,
    JWT_SECRET_KEY="test-secret-key-that-is-long-enough-for-testing-only",
    ADMIN_BOOTSTRAP_ENABLED="false",
    DB_ECHO="false",
    AUTO_CREATE_TABLES="false",
    RATE_LIMIT_ENABLED="false",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.models.enums import AccountStatus, UserRole, VerificationStatus  # noqa: E402


@pytest.fixture(autouse=True)
def clean_schema():
    """Fresh schema for every test — guarantees isolation and real constraints."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def make_user(
    db: Session,
    *,
    email: str | None = None,
    role: UserRole = UserRole.STUDENT,
    verified: bool = True,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex[:8]}@ssuet.edu.pk",
        password_hash=hash_password("Password123!"),
        phone=f"+92{uuid.uuid4().int % 10**10:010d}",
        full_name="Test User",
        role=role,
        department="Computer Science",
        university_id=f"SSUET-{uuid.uuid4().hex[:6].upper()}",
        is_university_email=True,
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
        ),
        account_status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin(client, db) -> dict:
    """A real ADMIN account that signs in through the normal login endpoint."""
    email = f"admin-{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("AdminPass123!"),
        phone=f"+9230{uuid.uuid4().int % 10**8:08d}",
        full_name="Console Admin",
        role=UserRole.ADMIN,
        department="Administration",
        university_id=f"ADM-{uuid.uuid4().hex[:5].upper()}",
        is_university_email=True,
        account_status=AccountStatus.ACTIVE,
        verification_status=VerificationStatus.VERIFIED,
    )
    db.add(user)
    db.commit()

    response = client.post("/api/v1/auth/login", json={"email": email, "password": "AdminPass123!"})
    assert response.status_code == 200, response.text
    body = response.json()
    body["headers"] = {"Authorization": f"Bearer {body['access_token']}"}
    return body
