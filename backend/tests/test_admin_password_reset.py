"""Admin fallback for password reset when email is not configured.

The admin issues a one-time code from the console; the member enters it on the
reset screen. It goes through the same token rules as the emailed link.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.enums import AccountStatus
from app.models.user import User
from tests.helpers import auth_header, register

ADMIN = "/api/v1/admin"


def _member(client) -> str:
    email = f"reset.{uuid.uuid4().hex[:8]}@ssuet.edu.pk"
    assert register(client, email=email).get("access_token")
    return email


def _user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email.lower()))


def test_admin_issues_code_and_member_resets_password(client, admin, db):
    email = _member(client)
    user = _user(db, email)

    response = client.post(f"{ADMIN}/users/{user.id}/password-reset-code", headers=admin["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["code"]) >= 20
    assert body["expires_in_minutes"] == 30

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": body["code"], "new_password": "BrandNew123"},
    )
    assert reset.status_code == 200, reset.text

    old = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    new = client.post("/api/v1/auth/login", json={"email": email, "password": "BrandNew123"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_issued_code_is_single_use(client, admin, db):
    email = _member(client)
    user = _user(db, email)
    code = client.post(f"{ADMIN}/users/{user.id}/password-reset-code", headers=admin["headers"]).json()["code"]

    first = client.post("/api/v1/auth/reset-password", json={"token": code, "new_password": "BrandNew123"})
    second = client.post("/api/v1/auth/reset-password", json={"token": code, "new_password": "Another456"})
    assert first.status_code == 200
    assert second.status_code == 422  # ValidationAppError, same as the emailed link


def test_code_is_refused_for_suspended_members(client, admin, db):
    email = _member(client)
    user = _user(db, email)
    user.account_status = AccountStatus.SUSPENDED
    db.commit()

    response = client.post(f"{ADMIN}/users/{user.id}/password-reset-code", headers=admin["headers"])
    assert response.status_code == 409


def test_unknown_member_is_404(client, admin):
    response = client.post(f"{ADMIN}/users/{uuid.uuid4()}/password-reset-code", headers=admin["headers"])
    assert response.status_code == 404


def test_members_cannot_issue_codes(client, admin, db):
    target = _member(client)
    actor = _member(client)
    token = client.post(
        "/api/v1/auth/login", json={"email": actor, "password": "Password123"}
    ).json()["access_token"]
    user = _user(db, target)

    response = client.post(f"{ADMIN}/users/{user.id}/password-reset-code", headers=auth_header(token))
    assert response.status_code in (401, 403)


def test_reset_accepts_any_password_and_member_can_log_in(client, admin, db):
    """Password policy is relaxed: a short, letters-only password works end to end."""
    email = _member(client)
    user = _user(db, email)
    code = client.post(f"{ADMIN}/users/{user.id}/password-reset-code", headers=admin["headers"]).json()["code"]

    reset = client.post("/api/v1/auth/reset-password", json={"token": code, "new_password": "abc"})
    assert reset.status_code == 200, reset.text

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "abc"})
    assert login.status_code == 200, login.text
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"}).status_code == 401
