"""Phase 6 — admin console API tests (§16, §17).

The console is the most dangerous surface in the product: it can verify people,
suspend accounts and cancel journeys. These tests therefore focus as much on the
guard rails (403 for members, 401 for anonymous, audit rows for every mutation) as
on the happy paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.admin_action import AdminAction
from app.models.enums import AccountStatus, ReportCategory, ReportStatus, UserRole
from app.models.report import Report
from tests.helpers import passenger_setup, register

ADMIN = "/api/v1/admin"


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client, *, depart_in_minutes: int = 300):
    driver, vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=depart_in_minutes)}
    )
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]).json()
    return driver, passenger, ride, trip


def file_report(client, db, reporter, reported) -> uuid.UUID:
    report = Report(
        reporter_id=uuid.UUID(reporter["user"]["id"]),
        reported_user_id=uuid.UUID(reported["user"]["id"]),
        category=ReportCategory.INAPPROPRIATE_BEHAVIOR,
        description="Was rude during the trip.",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report.id


# ------------------------------------------------------------------- guard rails
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", f"{ADMIN}/dashboard"),
        ("get", f"{ADMIN}/users"),
        ("get", f"{ADMIN}/verifications"),
        ("get", f"{ADMIN}/vehicles"),
        ("get", f"{ADMIN}/rides"),
        ("get", f"{ADMIN}/trips"),
        ("get", f"{ADMIN}/reports"),
        ("get", f"{ADMIN}/admin-actions"),
        ("get", f"{ADMIN}/analytics"),
        ("get", f"{ADMIN}/settings"),
    ],
)
def test_admin_endpoints_require_authentication(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_members_cannot_reach_the_console(client, admin):
    member = register(client)
    assert client.get(f"{ADMIN}/dashboard", headers=member["headers"]).status_code == 403
    assert client.get(f"{ADMIN}/users", headers=member["headers"]).status_code == 403
    assert client.get(f"{ADMIN}/ping", headers=admin["headers"]).status_code == 200
    assert client.get(f"{ADMIN}/ping", headers=member["headers"]).status_code == 403


# ------------------------------------------------------------------- dashboard
def test_dashboard_reports_live_numbers(client, admin):
    driver, passenger, ride, trip = matched_trip(client)

    body = client.get(f"{ADMIN}/dashboard", headers=admin["headers"]).json()
    stats = body["stats"]
    assert stats["total_users"] >= 3  # admin + driver + passenger
    assert stats["published_rides"] == 1
    assert stats["open_rides"] == 0  # the single ride is matched
    assert stats["active_trips"] == 1
    assert stats["rides_today"] == 1
    assert len(body["users_per_day"]) == 14
    assert body["trips_by_status"]["CONFIRMED"] == 1
    assert body["generated_at"]


def test_dashboard_counts_follow_real_changes(client, admin, db):
    before = client.get(f"{ADMIN}/dashboard", headers=admin["headers"]).json()["stats"]
    passenger_setup(client)
    after = client.get(f"{ADMIN}/dashboard", headers=admin["headers"]).json()["stats"]
    assert after["published_rides"] == before["published_rides"] + 1
    assert after["total_users"] == before["total_users"] + 1


def test_analytics_are_computed_from_data(client, admin):
    matched_trip(client)
    body = client.get(f"{ADMIN}/analytics?days=7", headers=admin["headers"]).json()
    assert body["days"] == 7
    assert len(body["users_per_day"]) == 7
    assert body["fuel_split"]["FREE"] == 1
    assert body["vehicle_split"]["CAR"] == 1
    assert body["direction_split"]["HOME_TO_UNIVERSITY"] == 1
    assert body["top_pickup_areas"][0]["area"] == "Gulshan-e-Iqbal"
    assert 0.0 <= body["completion_rate"] <= 100.0


def test_settings_expose_flags_not_secrets(client, admin):
    body = client.get(f"{ADMIN}/settings", headers=admin["headers"]).json()
    assert body["environment"] == "test"
    assert isinstance(body["features"], dict)
    assert "maps" in body["features"]
    # no secret material is ever serialised
    flat = str(body).lower()
    for secret in ("jwt", "password", "secret", "admin_password"):
        assert secret not in flat


# ----------------------------------------------------------------------- users
def test_user_search_and_filters(client, admin):
    driver, _vehicle, _ride = passenger_setup(client)
    register(client, department="Electrical Engineering")

    by_name = client.get(f"{ADMIN}/users?search=Test User", headers=admin["headers"]).json()
    assert by_name["total"] >= 2

    by_email = client.get(
        f"{ADMIN}/users?search={driver['user']['email']}", headers=admin["headers"]
    ).json()
    assert by_email["total"] == 1
    assert by_email["items"][0]["email"] == driver["user"]["email"]

    students = client.get(f"{ADMIN}/users?role=STUDENT", headers=admin["headers"]).json()
    assert all(item["role"] == "STUDENT" for item in students["items"])

    admins = client.get(f"{ADMIN}/users?role=ADMIN", headers=admin["headers"]).json()
    assert admins["total"] == 1

    verified = client.get(
        f"{ADMIN}/users?verification=VERIFIED", headers=admin["headers"]
    ).json()
    assert all(item["verification_status"] == "VERIFIED" for item in verified["items"])


def test_user_list_pagination(client, admin):
    for _ in range(3):
        register(client)
    page = client.get(f"{ADMIN}/users?page=1&limit=2", headers=admin["headers"]).json()
    assert page["limit"] == 2
    assert len(page["items"]) <= 2
    assert page["pages"] >= 2
    second = client.get(f"{ADMIN}/users?page=2&limit=2", headers=admin["headers"]).json()
    assert {i["id"] for i in page["items"]} & {i["id"] for i in second["items"]} == set()


def test_user_dossier_contains_related_records(client, admin):
    driver, _passenger, _ride, _trip = matched_trip(client)
    detail = client.get(f"{ADMIN}/users/{driver['user']['id']}", headers=admin["headers"]).json()
    assert detail["user"]["full_name"] == driver["user"]["full_name"]
    assert len(detail["vehicles"]) == 1
    assert len(detail["recent_rides"]) == 1
    assert detail["trips_as_driver"] == 1
    assert detail["home_area"] == "Gulshan-e-Iqbal"


def test_unknown_user_is_404(client, admin):
    assert (
        client.get(f"{ADMIN}/users/{uuid.uuid4()}", headers=admin["headers"]).status_code == 404
    )


# ------------------------------------------------------------------ decisions
def test_verify_user_writes_audit_row_and_notifies(client, admin, db):
    member = register(client)
    db_user = db.get(__import__("app.models.user", fromlist=["User"]).User, uuid.UUID(member["user"]["id"]))
    db_user.verification_status = "PENDING"
    db.commit()

    response = client.post(
        f"{ADMIN}/users/{member['user']['id']}/verify",
        json={"note": "ID card checked"},
        headers=admin["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "VERIFIED"

    action = db.scalar(
        select(AdminAction).where(
            AdminAction.action_type == "VERIFY_USER",
            AdminAction.target_user_id == uuid.UUID(member["user"]["id"]),
        )
    )
    assert action is not None and action.notes == "ID card checked"

    notifications = client.get("/api/v1/notifications", headers=member["headers"]).json()
    assert any(item["type"] == "ACCOUNT_VERIFIED" for item in notifications["items"])


def test_verify_is_idempotent_guarded(client, admin):
    member = register(client)  # university domain → auto-verified
    response = client.post(f"{ADMIN}/users/{member['user']['id']}/verify", headers=admin["headers"])
    assert response.status_code == 409


def test_reject_user(client, admin, db):
    member = register(client)
    db_user = db.get(__import__("app.models.user", fromlist=["User"]).User, uuid.UUID(member["user"]["id"]))
    db_user.verification_status = "PENDING"
    db.commit()

    response = client.post(
        f"{ADMIN}/users/{member['user']['id']}/reject",
        json={"reason": "ID card unreadable"},
        headers=admin["headers"],
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "REJECTED"


def test_suspend_requires_reason_and_records_it(client, admin):
    member = register(client)

    missing = client.post(
        f"{ADMIN}/users/{member['user']['id']}/suspend", json={}, headers=admin["headers"]
    )
    assert missing.status_code == 422

    suspended = client.post(
        f"{ADMIN}/users/{member['user']['id']}/suspend",
        json={"reason": "Repeated no-shows"},
        headers=admin["headers"],
    )
    assert suspended.status_code == 200
    assert suspended.json()["account_status"] == "SUSPENDED"

    # the suspended member is locked out immediately
    blocked = client.get("/api/v1/auth/me", headers=member["headers"])
    assert blocked.status_code == 403

    listed = client.get(f"{ADMIN}/users?status=SUSPENDED", headers=admin["headers"]).json()
    assert listed["total"] == 1


def test_suspending_a_driver_cancels_their_open_rides(client, admin):
    driver, _vehicle, ride = passenger_setup(client)
    response = client.post(
        f"{ADMIN}/users/{driver['user']['id']}/suspend",
        json={"reason": "Safety investigation"},
        headers=admin["headers"],
    )
    assert response.status_code == 200
    rides = client.get(f"{ADMIN}/rides?status=CANCELLED", headers=admin["headers"]).json()
    assert rides["total"] == 1
    assert rides["items"][0]["id"] == ride["id"]


def test_reactivate_restores_access(client, admin):
    member = register(client)
    client.post(
        f"{ADMIN}/users/{member['user']['id']}/suspend",
        json={"reason": "Under review"},
        headers=admin["headers"],
    )
    restored = client.post(
        f"{ADMIN}/users/{member['user']['id']}/reactivate", headers=admin["headers"]
    )
    assert restored.status_code == 200
    assert restored.json()["account_status"] == "ACTIVE"
    assert client.get("/api/v1/auth/me", headers=member["headers"]).status_code == 200


def test_admin_accounts_cannot_be_suspended(client, admin):
    response = client.post(
        f"{ADMIN}/users/{admin['user']['id']}/suspend",
        json={"reason": "Trying to lock out the console"},
        headers=admin["headers"],
    )
    assert response.status_code == 409


# -------------------------------------------------------------- verifications
def test_verification_queue(client, admin, db):
    member = register(client)
    db_user = db.get(__import__("app.models.user", fromlist=["User"]).User, uuid.UUID(member["user"]["id"]))
    db_user.verification_status = "PENDING"

    from app.models.verification import Verification

    db.add(
        Verification(
            user_id=db_user.id,
            verification_type="STUDENT_ID",
            status="PENDING",
            submitted_value="SSUET-2026-001",
            document_url="https://example.com/id.jpg",
        )
    )
    db.commit()

    queue = client.get(f"{ADMIN}/verifications", headers=admin["headers"]).json()
    assert queue["total"] == 1
    row = queue["items"][0]
    assert row["user_name"] == member["user"]["full_name"]
    assert row["verification_type"] == "STUDENT_ID"

    client.post(f"{ADMIN}/users/{member['user']['id']}/verify", headers=admin["headers"])
    assert client.get(f"{ADMIN}/verifications", headers=admin["headers"]).json()["total"] == 0


# -------------------------------------------------------------------- vehicles
def test_vehicle_queue_and_decisions(client, admin):
    driver, vehicle, _ride = passenger_setup(client)

    queue = client.get(f"{ADMIN}/vehicles?status=PENDING", headers=admin["headers"]).json()
    assert queue["total"] == 1
    assert queue["items"][0]["owner_name"] == driver["user"]["full_name"]

    approved = client.post(f"{ADMIN}/vehicles/{vehicle['id']}/verify", headers=admin["headers"])
    assert approved.status_code == 200
    assert approved.json()["status"] == "VERIFIED"
    assert client.get(f"{ADMIN}/vehicles?status=PENDING", headers=admin["headers"]).json()["total"] == 0

    again = client.post(f"{ADMIN}/vehicles/{vehicle['id']}/verify", headers=admin["headers"])
    assert again.status_code == 409


def test_vehicle_rejection_requires_a_reason(client, admin):
    _driver, vehicle, _ride = passenger_setup(client)
    missing = client.post(f"{ADMIN}/vehicles/{vehicle['id']}/reject", json={}, headers=admin["headers"])
    assert missing.status_code == 422

    rejected = client.post(
        f"{ADMIN}/vehicles/{vehicle['id']}/reject",
        json={"reason": "Registration photo is unreadable"},
        headers=admin["headers"],
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["review_note"] == "Registration photo is unreadable"


def test_vehicle_search(client, admin):
    _driver, vehicle, _ride = passenger_setup(client)
    found = client.get(
        f"{ADMIN}/vehicles?search={vehicle['registration_number']}", headers=admin["headers"]
    ).json()
    assert found["total"] == 1


# ----------------------------------------------------------------------- rides
def test_ride_listing_with_filters(client, admin):
    _driver, _vehicle, ride = passenger_setup(client)
    matched_trip(client)

    all_rides = client.get(f"{ADMIN}/rides", headers=admin["headers"]).json()
    assert all_rides["total"] == 2

    open_rides = client.get(f"{ADMIN}/rides?status=OPEN", headers=admin["headers"]).json()
    assert open_rides["total"] == 1
    assert open_rides["items"][0]["id"] == ride["id"]

    matched = client.get(f"{ADMIN}/rides?status=MATCHED", headers=admin["headers"]).json()
    assert matched["total"] == 1
    assert matched["items"][0]["matched_passenger_name"] is not None

    by_area = client.get(f"{ADMIN}/rides?search=Gulshan", headers=admin["headers"]).json()
    assert by_area["total"] == 2

    by_direction = client.get(
        f"{ADMIN}/rides?direction=UNIVERSITY_TO_HOME", headers=admin["headers"]
    ).json()
    assert by_direction["total"] == 0


def test_ride_date_filter(client, admin):
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    passenger_setup(client, ride_overrides={"departure_at": tomorrow.isoformat()})

    tomorrow_date = tomorrow.date().isoformat()
    inside = client.get(f"{ADMIN}/rides?date_from={tomorrow_date}", headers=admin["headers"]).json()
    assert inside["total"] == 1

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    outside = client.get(f"{ADMIN}/rides?date_to={yesterday}", headers=admin["headers"]).json()
    assert outside["total"] == 0


def test_admin_force_cancel_ride_notifies_passenger(client, admin):
    driver, passenger, ride, _trip = matched_trip(client)

    response = client.post(
        f"{ADMIN}/rides/{ride['id']}/cancel",
        json={"reason": "Reported unsafe driving"},
        headers=admin["headers"],
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    trips = client.get(f"{ADMIN}/trips?status=CANCELLED", headers=admin["headers"]).json()
    assert trips["total"] == 1

    notifications = client.get("/api/v1/notifications", headers=passenger["headers"]).json()
    assert any(item["type"] == "TRIP_CANCELLED" for item in notifications["items"])


# ----------------------------------------------------------------------- trips
def test_trip_views(client, admin):
    _driver, _passenger, _ride, trip = matched_trip(client)

    active = client.get(f"{ADMIN}/trips?active_only=true", headers=admin["headers"]).json()
    assert active["total"] == 1
    assert active["items"][0]["driver_name"] and active["items"][0]["passenger_name"]

    client.post(f"/api/v1/trips/{trip['id']}/start", headers=_driver["headers"])
    client.post(f"/api/v1/trips/{trip['id']}/complete", headers=_driver["headers"])
    client.post(f"/api/v1/trips/{trip['id']}/complete", headers=_passenger["headers"])

    completed = client.get(f"{ADMIN}/trips?status=COMPLETED", headers=admin["headers"]).json()
    assert completed["total"] == 1
    assert completed["items"][0]["completed_at"] is not None
    assert client.get(f"{ADMIN}/trips?active_only=true", headers=admin["headers"]).json()["total"] == 0


# --------------------------------------------------------------------- reports
def test_report_queue_and_resolution(client, admin, db):
    reporter = register(client)
    reported = register(client)
    report_id = file_report(client, db, reporter, reported)

    queue = client.get(f"{ADMIN}/reports?status=OPEN", headers=admin["headers"]).json()
    assert queue["total"] == 1
    row = queue["items"][0]
    assert row["reporter_name"] == reporter["user"]["full_name"]
    assert row["reported_user_name"] == reported["user"]["full_name"]

    detail = client.get(f"{ADMIN}/reports/{report_id}", headers=admin["headers"])
    assert detail.status_code == 200

    needs_note = client.patch(
        f"{ADMIN}/reports/{report_id}", json={"status": "RESOLVED"}, headers=admin["headers"]
    )
    assert needs_note.status_code == 422

    resolved = client.patch(
        f"{ADMIN}/reports/{report_id}",
        json={"status": "RESOLVED", "resolution_note": "Waroed both members; no further action."},
        headers=admin["headers"],
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None


def test_report_status_filter(client, admin, db):
    reporter = register(client)
    reported = register(client)
    report_id = file_report(client, db, reporter, reported)
    client.patch(
        f"{ADMIN}/reports/{report_id}",
        json={"status": "DISMISSED", "resolution_note": "No evidence."},
        headers=admin["headers"],
    )
    assert client.get(f"{ADMIN}/reports?status=OPEN", headers=admin["headers"]).json()["total"] == 0
    assert client.get(f"{ADMIN}/reports?status=DISMISSED", headers=admin["headers"]).json()["total"] == 1


# ------------------------------------------------------------------ audit trail
def test_every_mutation_is_audited(client, admin, db):
    member = register(client)
    _driver, vehicle, _ride = passenger_setup(client)

    client.post(
        f"{ADMIN}/users/{member['user']['id']}/suspend",
        json={"reason": "Test suspension"},
        headers=admin["headers"],
    )
    client.post(f"{ADMIN}/vehicles/{vehicle['id']}/verify", headers=admin["headers"])

    log = client.get(f"{ADMIN}/admin-actions", headers=admin["headers"]).json()
    types = {item["action_type"] for item in log["items"]}
    assert {"SUSPEND_USER", "VERIFY_VEHICLE"} <= types
    assert all(item["admin_name"] == "Console Admin" for item in log["items"])
    assert log["items"][0]["created_at"]

    persisted = db.scalars(select(AdminAction)).all()
    assert len(persisted) >= 2


def test_audit_log_is_paginated(client, admin, db):
    member = register(client)
    for _ in range(3):
        client.post(f"{ADMIN}/users/{member['user']['id']}/suspend", json={"reason": "x" * 4}, headers=admin["headers"])
        client.post(f"{ADMIN}/users/{member['user']['id']}/reactivate", headers=admin["headers"])

    page = client.get(f"{ADMIN}/admin-actions?limit=2", headers=admin["headers"]).json()
    assert page["limit"] == 2
    assert page["total"] >= 4
    assert len(page["items"]) == 2
