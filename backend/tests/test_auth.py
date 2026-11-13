"""Phase 2 — authentication, sessions, verification and privacy tests (§23)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.api.deps import require_admin, require_verified_user
from app.core.exceptions import ForbiddenError
from app.models import User
from app.models.enums import AccountStatus, UserRole, VerificationStatus
from app.services import auth_service
from tests.conftest import make_user

VALID = {
    "full_name": "Ali Raza",
    "email": "ali.raza@ssuet.edu.pk",
    "password": "Password123",
    "phone": "+923001234567",
    "role": "STUDENT",
    "university_id": "2022F-Bcs-101",
    "department": "Computer Science",
    "semester": 5,
    "home_area": "Gulshan-e-Iqbal",
}


def register(client, **overrides):
    payload = {**VALID, **overrides}
    return client.post("/api/v1/auth/register", json=payload)


def auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# ------------------------------------------------------------------ register
def test_register_verified_university_email_returns_tokens(client):
    response = register(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == 30 * 60
    user = body["user"]
    assert user["email"] == "ali.raza@ssuet.edu.pk"
    assert user["verification_status"] == "VERIFIED"      # trusted domain
    assert user["role"] == "STUDENT"
    assert user["student_profile"]["semester"] == 5
    assert "password" not in user and "password_hash" not in user


def test_register_outside_domain_requires_manual_verification(client):
    body = register(client, email="someone@gmail.com").json()
    assert body["user"]["verification_status"] == "UNVERIFIED"
    assert body["user"]["is_university_email"] is False


def test_register_teacher_creates_teacher_profile(client):
    body = register(
        client,
        email="dr.faheem@ssuet.edu.pk",
        role="TEACHER",
        university_id="SSUET-EMP-1001",
        department="Computer Science",
        designation="Associate Professor",
        semester=None,
    ).json()
    assert body["user"]["teacher_profile"]["designation"] == "Associate Professor"
    assert body["user"]["student_profile"] is None


def test_duplicate_email_is_rejected(client):
    assert register(client).status_code == 201
    response = register(client, phone="+923009999999", university_id="2022F-Bcs-999")
    assert response.status_code == 422
    assert response.json()["error"]["details"]["email"] == "already registered"


def test_duplicate_phone_is_rejected(client):
    assert register(client).status_code == 201
    response = register(client, email="other@ssuet.edu.pk", university_id="2022F-Bcs-555")
    assert response.status_code == 422
    assert "phone" in response.json()["error"]["details"]


@pytest.mark.parametrize(
    "password",
    ["a", "lettersonly", "12345678901", "password1", "1", "   spaces inside   ", "x" * 128],
)
def test_any_reasonable_password_is_accepted(client, password):
    assert register(client, password=password).status_code == 201


@pytest.mark.parametrize("password", ["", "x" * 129])
def test_empty_or_oversized_passwords_are_rejected(client, password):
    assert register(client, password=password).status_code == 422


def test_admin_cannot_self_register(client):
    assert register(client, role="ADMIN").status_code == 422


# --------------------------------------------------------------------- login
def test_login_success(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "Password123"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_is_case_insensitive_on_email(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": "ALI.RAZA@SSUET.EDU.PK", "password": "Password123"}
    )
    assert response.status_code == 200


def test_login_wrong_password_and_unknown_email_are_indistinguishable(client):
    register(client)
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "WrongPass123"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@ssuet.edu.pk", "password": "WrongPass123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_suspended_user_cannot_log_in(client, db):
    register(client)
    user = db.scalar(select(User).where(User.email == "ali.raza@ssuet.edu.pk"))
    user.account_status = AccountStatus.SUSPENDED
    user.suspension_reason = "Report under investigation"
    db.commit()

    response = client.post(
        "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "Password123"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason_code"] == "ACCOUNT_SUSPENDED"


# ------------------------------------------------------- sessions & refresh
def test_me_requires_a_valid_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth_header("garbage")).status_code == 401


def test_me_returns_the_owner_view(client):
    body = register(client).json()
    me = client.get("/api/v1/auth/me", headers=auth_header(body["access_token"])).json()
    assert me["email"] == "ali.raza@ssuet.edu.pk"
    assert me["phone"] == "+923001234567"      # private, owner-only
    assert me["university_id"] == "2022F-Bcs-101"


def test_refresh_rotates_and_old_token_cannot_be_reused(client):
    first = register(client).json()
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != first["refresh_token"]

    # replaying the consumed token = theft → session family revoked
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401

    # ...and the freshly rotated token is dead too
    after = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert after.status_code == 401


def test_logout_revokes_the_refresh_token(client):
    body = register(client).json()
    assert client.post("/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]}).status_code == 200
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code
        == 401
    )


def test_logout_all_kills_every_session(client):
    body = register(client).json()
    second = client.post(
        "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "Password123"}
    ).json()
    assert client.post("/api/v1/auth/logout-all", headers=auth_header(body["access_token"])).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


# ------------------------------------------------------- password management
def test_forgot_password_does_not_leak_registration(client):
    register(client)
    known = client.post("/api/v1/auth/forgot-password", json={"email": "ali.raza@ssuet.edu.pk"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@ssuet.edu.pk"})
    assert known.status_code == unknown.status_code == 202
    assert known.json()["message"] == unknown.json()["message"]


def test_full_password_reset_flow(client, db, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        auth_service, "send_password_reset_email", lambda to, name, token: captured.update(token=token) or True
    )
    register(client)
    client.post("/api/v1/auth/forgot-password", json={"email": "ali.raza@ssuet.edu.pk"})
    assert "token" in captured

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "BrandNew123"},
    )
    assert response.status_code == 200

    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "Password123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "BrandNew123"}
        ).status_code
        == 200
    )


def test_reset_token_is_single_use(client, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        auth_service, "send_password_reset_email", lambda to, name, token: captured.update(token=token) or True
    )
    register(client)
    client.post("/api/v1/auth/forgot-password", json={"email": "ali.raza@ssuet.edu.pk"})

    first = client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "BrandNew123"},
    )
    second = client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "AnotherPass123"},
    )
    assert first.status_code == 200
    assert second.status_code == 422


def test_reset_invalidates_existing_sessions(client, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        auth_service, "send_password_reset_email", lambda to, name, token: captured.update(token=token) or True
    )
    body = register(client).json()
    client.post("/api/v1/auth/forgot-password", json={"email": "ali.raza@ssuet.edu.pk"})
    client.post("/api/v1/auth/reset-password", json={"token": captured["token"], "new_password": "BrandNew123"})
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    )


def test_reset_ends_an_outstanding_access_token_immediately(client, monkeypatch):
    """A stolen access token must stop working at the reset, not after its 30-minute expiry."""
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        auth_service, "send_password_reset_email", lambda to, name, token: captured.update(token=token) or True
    )
    body = register(client).json()
    old_headers = auth_header(body["access_token"])
    assert client.get("/api/v1/users/me", headers=old_headers).status_code == 200

    client.post("/api/v1/auth/forgot-password", json={"email": "ali.raza@ssuet.edu.pk"})
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "BrandNew123"},
    )
    assert reset.status_code == 200

    assert client.get("/api/v1/users/me", headers=old_headers).status_code == 401
    fresh = client.post(
        "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "BrandNew123"}
    ).json()
    assert client.get("/api/v1/users/me", headers=auth_header(fresh["access_token"])).status_code == 200


def test_change_password_requires_current_password(client):
    body = register(client).json()
    headers = auth_header(body["access_token"])
    bad = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "WrongPass123", "new_password": "AnotherPass123"},
        headers=headers,
    )
    assert bad.status_code == 422
    good = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Password123", "new_password": "AnotherPass123"},
        headers=headers,
    )
    assert good.status_code == 200


# ------------------------------------------------------- email verification
def test_email_verification_link_marks_the_address_confirmed(client, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        auth_service, "send_verification_email", lambda to, name, token: captured.update(token=token) or True
    )
    register(client)
    assert "token" in captured

    response = client.post("/api/v1/auth/verify-email", json={"token": captured["token"]})
    assert response.status_code == 200
    assert response.json()["email_verified_at"] is not None

    again = client.post("/api/v1/auth/verify-email", json={"token": captured["token"]})
    assert again.status_code == 422


# ------------------------------------------- manual university verification
def test_manual_verification_submission_moves_account_to_pending(client):
    body = register(client, email="bilal@gmail.com", university_id="2023F-Bcs-777").json()
    headers = auth_header(body["access_token"])

    response = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "submitted_value": "2023F-Bcs-777",
            "document_url": "https://cdn.ssuet-rideshare.test/ids/777.jpg",
            "note": "Card photo attached",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PENDING"
    assert client.get("/api/v1/auth/me", headers=headers).json()["verification_status"] == "PENDING"

    # a second submission while pending is rejected
    duplicate = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "document_url": "https://cdn.ssuet-rideshare.test/ids/777.jpg",
        },
        headers=headers,
    )
    assert duplicate.status_code == 422

    history = client.get("/api/v1/users/me/verifications", headers=headers).json()
    assert len(history) == 1


def test_verified_user_cannot_submit_again(client):
    body = register(client).json()
    response = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "document_url": "https://cdn.ssuet-rideshare.test/ids/1.jpg",
        },
        headers=auth_header(body["access_token"]),
    )
    assert response.status_code == 422


# -------------------------------------------------------- profile & privacy
def test_public_profile_hides_private_fields(client):
    me = register(client).json()
    other = register(
        client, email="ahmed@ssuet.edu.pk", phone="+923007777777", university_id="2022F-Bcs-222"
    ).json()
    viewer_headers = auth_header(other["access_token"])

    public = client.get(f"/api/v1/users/{me['user']['id']}/public", headers=viewer_headers)
    assert public.status_code == 200
    payload = public.json()
    assert payload["full_name"] == "Ali Raza"
    for forbidden in ("email", "phone", "university_id", "home_area", "suspension_reason"):
        assert forbidden not in payload


def test_profile_update_cannot_escalate_role_or_verification(client):
    body = register(client, email="escalate@ssuet.edu.pk", university_id="2022F-Bcs-333").json()
    headers = auth_header(body["access_token"])

    response = client.patch(
        "/api/v1/users/me",
        json={
            "full_name": "Ali Raza Khan",
            "role": "ADMIN",
            "verification_status": "VERIFIED",
            "completed_trips_count": 999,
            "rating_average": 5.0,
        },
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["full_name"] == "Ali Raza Khan"
    assert updated["role"] == "STUDENT"                    # ignored
    assert updated["completed_trips_count"] == 0           # ignored
    assert updated["rating_average"] == 0.0                # ignored


def test_profile_update_rejects_duplicate_phone(client):
    first = register(client).json()
    register(client, email="second@ssuet.edu.pk", phone="+923005555555", university_id="2022F-Bcs-444")
    response = client.patch(
        "/api/v1/users/me",
        json={"phone": "+923005555555"},
        headers=auth_header(first["access_token"]),
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ blocking
def test_block_and_unblock_flow(client):
    me = register(client).json()
    other = register(
        client, email="blocked@ssuet.edu.pk", phone="+923002222222", university_id="2022F-Bcs-555"
    ).json()
    headers = auth_header(me["access_token"])
    target = other["user"]["id"]

    assert client.post(f"/api/v1/users/{target}/block", headers=headers).status_code == 200
    assert client.post(f"/api/v1/users/{target}/block", headers=headers).status_code == 409
    blocked = client.get("/api/v1/users/me/blocks", headers=headers).json()
    assert [b["id"] for b in blocked] == [target]

    assert client.delete(f"/api/v1/users/{target}/block", headers=headers).status_code == 200
    assert client.get("/api/v1/users/me/blocks", headers=headers).json() == []


def test_cannot_block_self(client):
    me = register(client).json()
    response = client.post(f"/api/v1/users/{me['user']['id']}/block", headers=auth_header(me["access_token"]))
    assert response.status_code == 422


# ------------------------------------------------- authorization dependencies
def test_require_verified_user_blocks_unverified_accounts(db):
    unverified = make_user(db, verified=False)
    verified = make_user(db, verified=True)

    with pytest.raises(ForbiddenError) as excinfo:
        require_verified_user(unverified)
    assert excinfo.value.details["reason_code"] == "ACCOUNT_NOT_VERIFIED"
    assert require_verified_user(verified).id == verified.id


def test_require_admin_blocks_regular_users(db):
    student = make_user(db)
    admin = make_user(db, role=UserRole.ADMIN)
    with pytest.raises(ForbiddenError):
        require_admin(student)
    assert require_admin(admin).id == admin.id


def test_suspended_user_token_is_rejected_mid_session(client, db):
    body = register(client).json()
    user = db.scalar(select(User).where(User.id == uuid.UUID(body["user"]["id"])))
    user.account_status = AccountStatus.SUSPENDED
    db.commit()

    response = client.get("/api/v1/auth/me", headers=auth_header(body["access_token"]))
    assert response.status_code == 403


# ---------------------------------------------------------------- rate limits
def test_login_rate_limit_returns_envelope(client):
    from app.core.rate_limit import limiter

    limiter.enabled = True
    try:
        register(client)
        statuses = [
            client.post(
                "/api/v1/auth/login",
                json={"email": "ali.raza@ssuet.edu.pk", "password": "WrongPass123"},
            ).status_code
            for _ in range(32)
        ]
        assert 429 in statuses
        limited = client.post(
            "/api/v1/auth/login", json={"email": "ali.raza@ssuet.edu.pk", "password": "WrongPass123"}
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"
    finally:
        limiter.enabled = False


# ------------------------------------------------------------------ unit-level
def test_passwords_are_never_returned_or_stored_in_plaintext(client, db):
    body = register(client).json()
    assert "password" not in str(body).lower().replace("password123", "")
    user = db.scalar(select(User).where(User.email == "ali.raza@ssuet.edu.pk"))
    assert user.password_hash.startswith("$argon2")
    assert "Password123" not in user.password_hash


def test_verification_status_defaults_for_new_accounts(db):
    user = make_user(db, verified=False)
    assert user.verification_status is VerificationStatus.PENDING
