"""Phase 7 — reports, complaints & blocking (§15).

Filing a complaint must be easy for the reporter and strictly bounded by the API:
you can only report somebody you actually travelled with, you cannot flood the
queue, and the office's decision comes back to you.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.enums import ReportStatus
from app.models.report import Report
from tests.helpers import passenger_setup, publish, register


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client):
    driver, _vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=15)}
    )
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(
        f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]
    ).json()
    return driver, passenger, ride, trip


# --------------------------------------------------------------------- create
def test_passenger_reports_driver_by_trip(client, db):
    driver, passenger, _ride, trip = matched_trip(client)

    response = client.post(
        "/api/v1/reports",
        json={
            "category": "MISLEADING_RIDE",
            "description": "The driver took a completely different route and asked for more fuel money.",
            "trip_id": trip["id"],
        },
        headers=passenger["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "OPEN"
    assert body["reported_user"]["id"] == driver["user"]["id"]
    assert body["trip_id"] == trip["id"]
    assert body["resolution_note"] is None
    # the reporter's own view of the reported member carries no contact details
    assert "phone" not in body["reported_user"]

    stored = db.scalar(select(Report))
    assert stored is not None
    assert stored.reported_user_id == uuid.UUID(driver["user"]["id"])
    assert stored.status is ReportStatus.OPEN


def test_driver_reports_passenger_by_trip(client):
    driver, passenger, _ride, trip = matched_trip(client)
    response = client.post(
        "/api/v1/reports",
        json={
            "category": "INAPPROPRIATE_BEHAVIOR",
            "description": "Passenger was rude to another member in the car.",
            "trip_id": trip["id"],
        },
        headers=driver["headers"],
    )
    assert response.status_code == 201
    assert response.json()["reported_user"]["id"] == passenger["user"]["id"]


def test_report_can_name_a_member_directly(client):
    driver, _vehicle, _ride = passenger_setup(client)
    reporter = register(client)
    response = client.post(
        "/api/v1/reports",
        json={
            "category": "FAKE_PROFILE",
            "description": "This profile uses a photograph of somebody else entirely.",
            "reported_user_id": driver["user"]["id"],
        },
        headers=reporter["headers"],
    )
    assert response.status_code == 201
    assert response.json()["reported_user"]["id"] == driver["user"]["id"]


def test_report_from_the_ride_context(client):
    driver, passenger, ride, _trip = matched_trip(client)
    response = client.post(
        "/api/v1/reports",
        json={
            "category": "SAFETY_CONCERN",
            "description": "Vehicle had a badly worn tyre and no spare.",
            "ride_id": ride["id"],
            "reported_user_id": driver["user"]["id"],
        },
        headers=passenger["headers"],
    )
    assert response.status_code == 201
    assert response.json()["ride_id"] == ride["id"]


def test_report_requires_a_target(client):
    member = register(client)
    response = client.post(
        "/api/v1/reports",
        json={"category": "OTHER", "description": "Something felt wrong on the journey today."},
        headers=member["headers"],
    )
    assert response.status_code == 422


def test_cannot_report_yourself(client):
    member = register(client)
    response = client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "Testing the self-report guard on this endpoint.",
            "reported_user_id": member["user"]["id"],
        },
        headers=member["headers"],
    )
    assert response.status_code == 422
    assert "yourself" in response.json()["error"]["message"].lower()


def test_cannot_report_a_stranger_through_someone_elses_trip(client):
    _driver, _passenger, _ride, trip = matched_trip(client)
    intruder = register(client)
    response = client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "I was never on this trip but I am filing anyway.",
            "trip_id": trip["id"],
        },
        headers=intruder["headers"],
    )
    assert response.status_code == 403


def test_reported_member_must_belong_to_the_trip(client):
    _driver, _passenger, _ride, trip = matched_trip(client)
    outsider = register(client)
    passenger_headers = client.post(
        "/api/v1/auth/login",
        json={"email": _passenger["user"]["email"], "password": "Password123"},
    ).json()
    headers = {"Authorization": f"Bearer {passenger_headers['access_token']}"}

    response = client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "Trying to attach an unrelated member to this trip.",
            "trip_id": trip["id"],
            "reported_user_id": outsider["user"]["id"],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_duplicate_open_report_is_refused(client):
    driver, passenger, _ride, _trip = matched_trip(client)
    payload = {
        "category": "HARASSMENT",
        "description": "Repeated unwanted messages after the trip ended.",
        "reported_user_id": driver["user"]["id"],
    }
    first = client.post("/api/v1/reports", json=payload, headers=passenger["headers"])
    assert first.status_code == 201

    second = client.post("/api/v1/reports", json=payload, headers=passenger["headers"])
    assert second.status_code == 409
    assert "open report" in second.json()["error"]["message"].lower()


def test_description_bounds_are_enforced(client):
    member = register(client)
    other = register(client)
    short = client.post(
        "/api/v1/reports",
        json={"category": "OTHER", "description": "bad", "reported_user_id": other["user"]["id"]},
        headers=member["headers"],
    )
    assert short.status_code == 422

    long = client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "x" * 1001,
            "reported_user_id": other["user"]["id"],
        },
        headers=member["headers"],
    )
    assert long.status_code == 422


def test_reporter_and_admins_are_notified(client, admin):
    driver, passenger, _ride, _trip = matched_trip(client)
    client.post(
        "/api/v1/reports",
        json={
            "category": "SAFETY_CONCERN",
            "description": "Brakes were making a grinding noise the entire way.",
            "reported_user_id": driver["user"]["id"],
        },
        headers=passenger["headers"],
    )

    reporter_inbox = client.get("/api/v1/notifications", headers=passenger["headers"]).json()
    assert any(item["type"] == "REPORT_RECEIVED" for item in reporter_inbox["items"])

    admin_inbox = client.get("/api/v1/notifications", headers=admin["headers"]).json()
    assert any(item["title"] == "New report filed" for item in admin_inbox["items"])


# ----------------------------------------------------------------------- read
def test_reporter_sees_their_own_reports_only(client):
    reporter = register(client)
    other = register(client)
    target = register(client)
    client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "Filed by the first reporter for this test.",
            "reported_user_id": target["user"]["id"],
        },
        headers=reporter["headers"],
    )

    mine = client.get("/api/v1/reports", headers=reporter["headers"]).json()
    assert mine["total"] == 1

    theirs = client.get("/api/v1/reports", headers=other["headers"]).json()
    assert theirs["total"] == 0


def test_report_detail_is_owner_only(client):
    reporter = register(client)
    target = register(client)
    created = client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "Owner-only detail check for the reports endpoint.",
            "reported_user_id": target["user"]["id"],
        },
        headers=reporter["headers"],
    ).json()

    assert client.get(
        f"/api/v1/reports/{created['id']}", headers=reporter["headers"]
    ).status_code == 200
    assert client.get(
        f"/api/v1/reports/{created['id']}", headers=target["headers"]
    ).status_code == 404


def test_status_filter_on_my_reports(client):
    reporter = register(client)
    target = register(client)
    client.post(
        "/api/v1/reports",
        json={
            "category": "OTHER",
            "description": "Open report used for the status filter test.",
            "reported_user_id": target["user"]["id"],
        },
        headers=reporter["headers"],
    )
    assert client.get("/api/v1/reports?status=OPEN", headers=reporter["headers"]).json()["total"] == 1
    assert (
        client.get("/api/v1/reports?status=RESOLVED", headers=reporter["headers"]).json()["total"] == 0
    )


def test_report_requires_authentication(client):
    assert client.post("/api/v1/reports", json={"category": "OTHER", "description": "x" * 20}).status_code == 401


# --------------------------------------------------------- resolution loop
def test_resolution_reaches_the_reporter(client, admin):
    driver, passenger, _ride, _trip = matched_trip(client)
    created = client.post(
        "/api/v1/reports",
        json={
            "category": "INAPPROPRIATE_BEHAVIOR",
            "description": "The driver shouted at me in front of other students.",
            "reported_user_id": driver["user"]["id"],
        },
        headers=passenger["headers"],
    ).json()

    # the office sees it in the queue immediately
    queue = client.get("/api/v1/admin/reports?status=OPEN", headers=admin["headers"]).json()
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == created["id"]

    resolved = client.patch(
        f"/api/v1/admin/reports/{created['id']}",
        json={"status": "RESOLVED", "resolution_note": "Spoke to the driver; warning issued."},
        headers=admin["headers"],
    )
    assert resolved.status_code == 200

    # the reporter is told the outcome, with the office's note
    detail = client.get(f"/api/v1/reports/{created['id']}", headers=passenger["headers"]).json()
    assert detail["status"] == "RESOLVED"
    assert detail["resolution_note"] == "Spoke to the driver; warning issued."
    assert detail["resolved_at"] is not None

    inbox = client.get("/api/v1/notifications", headers=passenger["headers"]).json()
    updates = [item for item in inbox["items"] if item["type"] == "REPORT_RESOLVED"]
    assert updates and "spoken" in updates[0]["body"].lower() or "warning" in updates[0]["body"].lower()


def test_a_new_report_is_allowed_after_the_previous_one_is_closed(client, admin):
    driver, passenger, _ride, _trip = matched_trip(client)
    payload = {
        "category": "OTHER",
        "description": "First complaint about the same member.",
        "reported_user_id": driver["user"]["id"],
    }
    first = client.post("/api/v1/reports", json=payload, headers=passenger["headers"]).json()
    client.patch(
        f"/api/v1/admin/reports/{first['id']}",
        json={"status": "DISMISSED", "resolution_note": "No evidence found."},
        headers=admin["headers"],
    )

    second = client.post(
        "/api/v1/reports",
        headers=passenger["headers"],
        json={**payload, "description": "Second complaint after the first was closed."},
    )
    assert second.status_code == 201


# ------------------------------------------------------------------- blocking
def test_blocking_prevents_matching_and_messaging(client):
    driver, _vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=15)}
    )
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(
        f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]
    ).json()

    # a second, still-open ride by the same driver — this is what Explore shows
    open_ride = publish(
        client,
        driver["headers"],
        _vehicle["id"],
        departure_at=iso(hours=6),
        pickup_area="North Nazimabad",
    )

    blocked = client.post(
        f"/api/v1/users/{driver['user']['id']}/block", headers=passenger["headers"]
    )
    assert blocked.status_code == 200

    # a blocked pair cannot exchange chat messages on an existing trip
    conversation_id = client.get(f"/api/v1/trips/{trip['id']}", headers=passenger["headers"]).json()[
        "conversation_id"
    ]
    assert conversation_id
    send = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"body": "Are we still on for tomorrow?"},
        headers=passenger["headers"],
    )
    assert send.status_code == 403

    # the driver's rides disappear from the blocker's explore feed
    feed = client.get("/api/v1/rides", headers=passenger["headers"]).json()
    assert open_ride["id"] not in [item["id"] for item in feed["items"]]

    assert client.delete(
        f"/api/v1/users/{driver['user']['id']}/block", headers=passenger["headers"]
    ).status_code == 200
    feed_after = client.get("/api/v1/rides", headers=passenger["headers"]).json()
    assert open_ride["id"] in [item["id"] for item in feed_after["items"]]


def test_block_list_and_double_block(client):
    member = register(client)
    other = register(client)
    client.post(f"/api/v1/users/{other['user']['id']}/block", headers=member["headers"])

    blocks = client.get("/api/v1/users/me/blocks", headers=member["headers"]).json()
    assert [item["id"] for item in blocks] == [other["user"]["id"]]

    again = client.post(f"/api/v1/users/{other['user']['id']}/block", headers=member["headers"])
    assert again.status_code == 409


def test_cannot_block_yourself(client):
    member = register(client)
    response = client.post(
        f"/api/v1/users/{member['user']['id']}/block", headers=member["headers"]
    )
    assert response.status_code in (400, 422)
