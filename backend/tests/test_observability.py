"""Observability: request correlation and the operations health panel (doc 18).

Two promises are tested here:

* every response carries a request id — the one the caller sent if there was one — plus
  a timing header, so a screenshot can be matched to a log line;
* `GET /admin/health` tells an operator the things that actually break in production
  (slow database, schema behind head, full disk, swollen queues) in one call, and is
  admin-only.
"""

from __future__ import annotations

import uuid

import pytest

from app.core import runtime
from tests.helpers import auth_header, register


# --------------------------------------------------------------- request ids
def test_response_carries_generated_request_id_and_timing(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 12
    assert float(response.headers["X-Process-Time-Ms"]) >= 0
    assert response.headers["Server-Timing"].startswith("app;dur=")


def test_incoming_request_id_is_propagated_unchanged(client):
    # nginx passes X-Request-ID through, so support can follow one request end to end
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc123def456"})
    assert response.headers["X-Request-ID"] == "abc123def456"


def test_request_id_is_unique_per_request(client):
    first = client.get("/api/v1/health").headers["X-Request-ID"]
    second = client.get("/api/v1/health").headers["X-Request-ID"]
    assert first != second


def test_errors_carry_a_request_id_too(client):
    response = client.get("/api/v1/users/me")  # no token → 401
    assert response.status_code == 401
    assert response.headers.get("X-Request-ID")


# ------------------------------------------------------------ health panel
def test_health_panel_is_admin_only(client):
    member = register(client)
    assert client.get("/api/v1/admin/health", headers=member["headers"]).status_code == 403
    assert client.get("/api/v1/admin/health").status_code == 401


def test_health_panel_reports_database_and_schema(client, admin):
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()

    assert body["status"] == "ok"
    assert body["database"]["ok"] is True
    assert body["database"]["latency_ms"] >= 0
    assert body["database"]["dialect"] in {"sqlite", "postgresql"}
    # the head is read from the migrations on disk: the panel can say "you are behind"
    assert body["database"]["schema_head"]
    assert body["version"] and body["environment"]
    assert body["process"]["uptime_seconds"] >= 0


def test_health_panel_counts_the_queues(client, admin, db):
    from tests.conftest import make_user
    from app.models.enums import VerificationStatus

    make_user(db, email=f"pending-{uuid.uuid4().hex[:6]}@gmail.com", verified=False)
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()

    assert body["queues"]["members"] >= 2
    assert body["queues"]["members_awaiting_verification"] >= 1
    assert set(body["queues"]) >= {
        "pending_verification_requests",
        "members_awaiting_verification",
        "pending_vehicles",
        "open_reports",
        "open_rides",
        "matching_rides",
        "trips_in_progress",
        "members",
    }


def test_health_panel_reports_media_and_disk(client, admin, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"), raising=False)
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()

    assert body["media"]["files"] == 0
    assert body["media"]["orphans"] == 0
    assert body["media"]["disk_free_bytes"] is None or body["media"]["disk_free_bytes"] > 0
    assert body["media"]["retention_days"] == settings.MEDIA_ORPHAN_RETENTION_DAYS


def test_health_panel_warns_when_the_schema_is_behind(client, admin, db):
    """A deployment that forgot `alembic upgrade head` must say so, loudly."""
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()
    head = body["database"]["schema_head"]
    assert body["database"]["schema_revision"] != head  # test DB is created, not migrated

    warnings = body["warnings"]
    assert any("alembic upgrade head" in warning for warning in warnings), warnings


def test_health_panel_surfaces_the_last_housekeeping_run(client, admin):
    runtime.record_maintenance(
        {"expired_rides": 2, "withdrawn_requests": 1, "auto_completed_trips": 0,
         "abandoned_trips": 0, "orphaned_media": 3}
    )
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()

    assert body["housekeeping"]["last_run_at"] is not None
    assert body["housekeeping"]["last_result"]["orphaned_media"] == 3
    assert not any("housekeeping" in warning for warning in body["warnings"])


def test_health_panel_status_degrades_on_a_slow_database(client, admin, monkeypatch):
    from app.services import system_service

    monkeypatch.setattr(system_service, "_SLOW_DB_MS", -1.0)  # force the slow branch
    body = client.get("/api/v1/admin/health", headers=admin["headers"]).json()

    assert body["status"] == "degraded"
    assert any("round-trip" in warning for warning in body["warnings"])


def test_liveness_probe_stays_cheap_and_unauthenticated(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # the probe must never touch the database: it answers even while the DB is down
    assert "database" not in response.json()
