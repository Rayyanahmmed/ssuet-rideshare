"""Phase 1 system tests: configuration, health endpoints, security primitives."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_readiness_checks_database(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_meta_exposes_university_and_feature_flags(client):
    body = client.get("/api/v1/meta").json()
    assert body["university"]["short_name"] == "SSUET"
    assert body["features"]["max_confirmed_passengers"] == 1
    assert "maps_configured" in body["features"]


def test_swagger_docs_available(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_unknown_route_returns_404(client):
    assert client.get("/api/v1/does-not-exist").status_code == 404


# ------------------------------- security -------------------------------
def test_password_hashing_is_salted_and_verifiable():
    first = hash_password("Password123!")
    second = hash_password("Password123!")
    assert first != second                    # unique salt
    assert first.startswith("$argon2")
    assert verify_password("Password123!", first)
    assert not verify_password("password123!", first)


def test_access_token_roundtrip_and_role():
    token, expires_at = create_access_token(subject="8b1f4a44-0000-0000-0000-000000000001", role="TEACHER")
    payload = decode_access_token(token)
    assert payload["sub"] == "8b1f4a44-0000-0000-0000-000000000001"
    assert payload["role"] == "TEACHER"
    assert payload["type"] == "access"
    assert expires_at > __import__("datetime").datetime.now(__import__("datetime").timezone.utc)


def test_tampered_token_is_rejected():
    from jose import JWTError

    token, _ = create_access_token(subject="abc", role="STUDENT")
    with pytest.raises(JWTError):
        decode_access_token(token + "tampered")


def test_refresh_tokens_are_hashed_not_stored_raw():
    raw, hashed = generate_refresh_token()
    assert raw != hashed
    assert hashed == hash_token(raw)
    assert len(hashed) == 64


# ------------------------------- config ---------------------------------
def test_production_rejects_placeholder_jwt_secret():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="CHANGE_ME", ADMIN_PASSWORD="x")


def test_production_rejects_short_jwt_secret():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="short", ADMIN_PASSWORD="x")


def test_production_requires_admin_password_when_bootstrap_enabled():
    with pytest.raises(ValueError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 40,
            ADMIN_BOOTSTRAP_ENABLED=True,
            ADMIN_PASSWORD="",
        )


def test_university_domain_detection():
    settings = Settings(UNIVERSITY_EMAIL_DOMAINS="ssuet.edu.pk, students.ssuet.edu.pk")
    assert settings.university_domains == ["ssuet.edu.pk", "students.ssuet.edu.pk"]


def test_maps_feature_flag_follows_the_live_console_setting(client, admin):
    """§13: the flag is read from the database, not from a build-time environment key."""
    assert client.get("/api/v1/meta").json()["features"]["maps_configured"] is True

    client.put(
        "/api/v1/admin/integrations/maps",
        headers=admin["headers"],
        json={"provider": "geoapify"},  # needs a key, and none is stored yet
    )
    assert client.get("/api/v1/meta").json()["features"]["maps_configured"] is False

    client.put(
        "/api/v1/admin/integrations/maps",
        headers=admin["headers"],
        json={"api_key": "fresh-key"},
    )
    assert client.get("/api/v1/meta").json()["features"]["maps_configured"] is True

    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"enabled": False})
    assert client.get("/api/v1/meta").json()["features"]["maps_configured"] is False
