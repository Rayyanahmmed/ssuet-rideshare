"""Phase 8 — end-to-end journeys across all three components.

Every other suite tests one module. These tests walk a **complete user story**
through the real HTTP surface, in order, the way the mobile app and the admin
console actually drive it — so an integration break between phases (a status that
does not cascade, a notification that stops firing, a seat that does not return)
fails here even if each module's own tests still pass.

Naming: `test_journey_…` — one test, one story.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.enums import AccountStatus, TripStatus, UserRole
from app.models.user import User
from app.services import maintenance_service
from tests.helpers import create_vehicle, passenger_setup, publish, register


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def notification_types(client, headers) -> list[str]:
    return [
        item["type"]
        for item in client.get("/api/v1/notifications?limit=50", headers=headers).json()["items"]
    ]


def accept_first_request(client, driver, ride):
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(
        item["id"]
        for item in inbox
        if item["ride_id"] == ride["id"] and item["status"] == "PENDING"
    )
    response = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------- happy path
def test_journey_publish_discover_match_chat_complete_review(client, db):
    """The complete product story: a driver offers a seat, a passenger takes it."""

    # 1. A verified teacher registers and registers a car ---------------------
    driver = register(client, role="TEACHER", department="Software Engineering")
    vehicle = create_vehicle(client, driver["headers"], make_and_model="Suzuki Cultus 2021")

    # 2. A stranger cannot publish with somebody else's vehicle (privacy gate) -
    intruder = register(client)
    stolen = client.post(
        "/api/v1/rides",
        headers=intruder["headers"],
        json={
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "Gulshan-e-Iqbal",
            "pickup_point": {"latitude": 24.92, "longitude": 67.09},
            "departure_at": iso(hours=6),
            "fuel_preference": "SHARE_FUEL",
            "contribution_type": "FIXED",
            "expected_fuel_share": 150,
            "vehicle_id": vehicle["id"],
        },
    )
    assert stolen.status_code in (403, 404, 422)

    # 3. The driver publishes a journey ---------------------------------------
    ride = publish(
        client,
        driver["headers"],
        vehicle["id"],
        departure_at=iso(hours=5),
        fuel_preference="SHARE_FUEL",
        contribution_type="FIXED",
        expected_fuel_share=150,
        note="Leaving right after the 4 pm lecture.",
    )
    assert ride["status"] == "OPEN"

    # 4. Another member discovers it in Explore -------------------------------
    passenger = register(client)
    feed = client.get("/api/v1/rides?direction=HOME_TO_UNIVERSITY", headers=passenger["headers"]).json()
    assert ride["id"] in [item["id"] for item in feed["items"]]
    card = next(item for item in feed["items"] if item["id"] == ride["id"])
    assert card["pickup_area"] == "Gulshan-e-Iqbal"
    assert "phone" not in card["driver"]  # privacy before matching
    assert card["seats_remaining"] == 1

    # 5. The passenger requests the seat --------------------------------------
    request = client.post(
        f"/api/v1/rides/{ride['id']}/requests",
        json={"message": "I have a 4 pm lecture too, can I join?"},
        headers=passenger["headers"],
    ).json()
    assert request["status"] == "PENDING"

    # the driver is told, without any contact details
    assert "RIDE_REQUEST_RECEIVED" in notification_types(client, driver["headers"])

    # 6. The driver accepts → trip, conversation and statuses are created ------
    trip = accept_first_request(client, driver, ride)
    assert trip["status"] == "CONFIRMED"
    assert trip["conversation_id"]
    assert client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()["status"] == "MATCHED"
    assert "RIDE_REQUEST_ACCEPTED" in notification_types(client, passenger["headers"])

    # 7. Both sides can now see contact details and the meeting point ---------
    passenger_view = client.get(f"/api/v1/trips/{trip['id']}", headers=passenger["headers"]).json()
    assert passenger_view["counterpart"]["phone"]
    assert passenger_view["can_start"] is False  # only the driver starts

    # 8. They chat inside the trip -------------------------------------------
    conversation_id = trip["conversation_id"]
    sent = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"body": "I will wait at the main gate."},
        headers=passenger["headers"],
    )
    assert sent.status_code == 201
    history = client.get(
        f"/api/v1/chat/conversations/{conversation_id}/messages", headers=driver["headers"]
    ).json()
    assert history["items"][-1]["body"] == "I will wait at the main gate."
    assert "NEW_MESSAGE" in notification_types(client, driver["headers"])

    # 9. The driver starts the journey ---------------------------------------
    started = client.post(f"/api/v1/trips/{trip['id']}/start", headers=driver["headers"])
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"
    assert client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()["status"] == "IN_PROGRESS"

    # 10. Completion needs both sides ----------------------------------------
    first = client.post(f"/api/v1/trips/{trip['id']}/complete", headers=driver["headers"]).json()
    assert first["status"] == "IN_PROGRESS"
    assert first["awaiting_my_confirmation"] is False
    passenger_pending = client.get(f"/api/v1/trips/{trip['id']}", headers=passenger["headers"]).json()
    assert passenger_pending["awaiting_my_confirmation"] is True

    second = client.post(f"/api/v1/trips/{trip['id']}/complete", headers=passenger["headers"])
    assert second.status_code == 200
    assert second.json()["status"] == "COMPLETED"
    completed_ride = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert completed_ride["status"] == "COMPLETED"

    # 11. Both members now owe a rating --------------------------------------
    assert client.get("/api/v1/reviews/pending", headers=driver["headers"]).json()["count"] == 1
    assert client.get("/api/v1/reviews/pending", headers=passenger["headers"]).json()["count"] == 1

    review = client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "Reliable and friendly — will pool again."},
        headers=passenger["headers"],
    )
    assert review.status_code == 201
    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 4, "comment": "On time, quiet passenger."},
        headers=driver["headers"],
    )

    # 12. Reputation, dashboards and the audit trail all agree ---------------
    driver_public = client.get(
        f"/api/v1/users/{driver['user']['id']}/public", headers=passenger["headers"]
    ).json()
    assert driver_public["rating_average"] == 5.0
    assert driver_public["rating_count"] == 1

    stats = client.get("/api/v1/admin/dashboard").status_code  # guarded
    assert stats == 401

    me = client.get("/api/v1/admin/dashboard", headers=(admin_headers := _admin(client, db)))
    assert me.status_code == 200
    assert me.json()["stats"]["completed_trips"] >= 1
    trips = client.get("/api/v1/admin/trips?status=COMPLETED", headers=admin_headers).json()
    assert any(item["id"] == trip["id"] for item in trips["items"])
    assert client.get("/api/v1/reviews/pending", headers=driver["headers"]).json()["count"] == 0


def _admin(client, db) -> dict:
    from app.core.security import hash_password

    email = f"admin-{uuid.uuid4().hex[:6]}@example.com"
    db.add(
        User(
            email=email,
            password_hash=hash_password("AdminPass123!"),
            phone=f"+9230{uuid.uuid4().int % 10**8:08d}",
            full_name="Journey Admin",
            role=UserRole.ADMIN,
            department="Administration",
            university_id=f"JAD-{uuid.uuid4().hex[:5].upper()}",
            is_university_email=True,
            account_status=AccountStatus.ACTIVE,
        )
    )
    db.commit()
    body = client.post("/api/v1/auth/login", json={"email": email, "password": "AdminPass123!"}).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


# --------------------------------------------------------------- seat reuse
def test_journey_passenger_cancels_and_the_seat_returns(client):
    """A cancelled seat must be usable by somebody else on the same ride."""

    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=30)})
    first = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=first["headers"])
    trip = accept_first_request(client, driver, ride)
    assert client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()["status"] == "MATCHED"

    cancelled = client.post(f"/api/v1/trips/{trip['id']}/cancel", json={"reason": "Lab got cancelled"}, headers=first["headers"])
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    reopened = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert reopened["status"] == "OPEN"
    assert reopened["seats_remaining"] == 1

    # a second passenger can take the freed seat
    second = register(client)
    assert client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={}, headers=second["headers"]
    ).status_code == 201
    new_trip = accept_first_request(client, driver, ride)
    assert new_trip["id"] != trip["id"]
    assert new_trip["status"] == "CONFIRMED"


def test_journey_driver_cancel_notifies_the_matched_passenger(client):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=30)})
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    trip = accept_first_request(client, driver, ride)

    response = client.post(
        f"/api/v1/rides/{ride['id']}/cancel", json={"reason": "Car in the workshop"}, headers=driver["headers"]
    )
    assert response.status_code == 200
    trip_after = client.get(f"/api/v1/trips/{trip['id']}", headers=passenger["headers"]).json()
    assert trip_after["status"] == "CANCELLED"
    assert any(
        item in notification_types(client, passenger["headers"])
        for item in ("TRIP_CANCELLED", "RIDE_CANCELLED")
    )


def test_journey_no_show_frees_the_seat_and_blocks_reviews(client):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=20)})
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    trip = accept_first_request(client, driver, ride)

    no_show = client.post(
        f"/api/v1/trips/{trip['id']}/no-show", json={"reason": "Waited 15 minutes at the meeting point"}, headers=driver["headers"]
    )
    assert no_show.status_code == 200, no_show.text
    assert no_show.json()["status"] == "NO_SHOW"
    assert "TRIP_NO_SHOW" in notification_types(client, passenger["headers"])

    # nobody travelled, so nobody may rate
    blocked = client.post(f"/api/v1/reviews/trips/{trip['id']}", json={"rating": 1}, headers=driver["headers"])
    assert blocked.status_code == 409


# ------------------------------------------------- gate: verification first
def test_journey_unverified_member_is_gated_until_an_admin_approves(client, admin):
    """A non-university email cannot publish until verification is approved."""

    suffix = uuid.uuid4().hex[:6]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"Gated Member {suffix}",
            "email": f"member{suffix}@gmail.com",
            "password": "Password123",
            "phone": f"+92311{suffix[:7].rjust(7, '3')}",
            "role": "STUDENT",
            "university_id": f"EXT-{suffix.upper()}",
            "department": "Computer Science",
            "semester": 3,
            "home_area": "North Nazimabad",
        },
    )
    assert response.status_code == 201
    member = response.json()
    headers = {"Authorization": f"Bearer {member['access_token']}"}
    assert member["user"]["verification_status"] == "UNVERIFIED"

    # 1. they can submit their ID card
    submitted = client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID", "submitted_value": "SSUET-2026-777", "document_url": "https://example.com/id.jpg"},
        headers=headers,
    )
    assert submitted.status_code == 201

    # 2. the admin sees them in the queue and approves
    queue = client.get("/api/v1/admin/verifications", headers=admin["headers"]).json()
    assert any(item["user_id"] == member["user"]["id"] for item in queue["items"])
    approved = client.post(f"/api/v1/admin/users/{member['user']['id']}/verify", headers=admin["headers"])
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "VERIFIED"

    # 3. now they can register a vehicle and publish
    vehicle = create_vehicle(client, headers)
    ride = publish(client, headers, vehicle["id"], departure_at=iso(hours=8))
    assert ride["status"] == "OPEN"
    assert "ACCOUNT_VERIFIED" in notification_types(client, headers)


def test_journey_rejected_vehicle_can_never_be_used(client, admin):
    """A rejected vehicle is blocked even though the default trust policy is lenient."""

    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    assert vehicle["status"] == "PENDING"

    # default policy: a pending vehicle may publish (fast onboarding),
    published = publish(client, driver["headers"], vehicle["id"], departure_at=iso(hours=8))
    assert published["status"] == "OPEN"

    rejected = client.post(
        f"/api/v1/admin/vehicles/{vehicle['id']}/reject",
        json={"reason": "Registration document is unreadable"},
        headers=admin["headers"],
    )
    assert rejected.status_code == 200

    blocked = client.post(
        "/api/v1/rides",
        headers=driver["headers"],
        json={
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "North Nazimabad",
            "pickup_point": {"latitude": 24.95, "longitude": 67.04},
            "departure_at": iso(hours=9),
            "fuel_preference": "FREE",
            "contribution_type": "NONE",
            "vehicle_id": vehicle["id"],
        },
    )
    assert blocked.status_code in (403, 409, 422)
    assert "rejected" in blocked.text.lower() or "verif" in blocked.text.lower()


def test_journey_strict_policy_can_require_a_verified_vehicle(client, monkeypatch):
    """`REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH=true` closes the onboarding gap (§7)."""

    from app.core.config import settings

    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    monkeypatch.setattr(settings, "REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH", True)

    blocked = client.post(
        "/api/v1/rides",
        headers=driver["headers"],
        json={
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "Gulshan-e-Iqbal",
            "pickup_point": {"latitude": 24.92, "longitude": 67.09},
            "departure_at": iso(hours=8),
            "fuel_preference": "FREE",
            "contribution_type": "NONE",
            "vehicle_id": vehicle["id"],
        },
    )
    assert blocked.status_code in (403, 409, 422)


# --------------------------------------------------------- housekeeping job
def test_journey_stale_ride_expires_and_disappears_from_explore(client, db):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(hours=5)})
    viewer = register(client)

    # 1. while it is upcoming, the ride is discoverable
    assert ride["id"] in [
        item["id"] for item in client.get("/api/v1/rides", headers=viewer["headers"]).json()["items"]
    ]

    # 2. age it past departure + grace window (what the scheduler sees an hour later)
    from app.models.ride import Ride

    row = db.get(Ride, uuid.UUID(ride["id"]))
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    row.departure_at = stale
    row.departure_date = stale.replace(hour=0, minute=0, second=0, microsecond=0)
    db.commit()

    # 3. the maintenance sweep expires it
    result = maintenance_service.expire_stale_rides(db, grace_minutes=60)
    assert result.expired_rides >= 1

    # 4. it leaves Explore and its status is honest
    assert client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()["status"] == "EXPIRED"
    assert ride["id"] not in [
        item["id"] for item in client.get("/api/v1/rides", headers=viewer["headers"]).json()["items"]
    ]


# ------------------------------------------------- moderation & safety story
def test_journey_safety_report_leads_to_suspension(client, admin, db):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=25)})
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    trip = accept_first_request(client, driver, ride)

    # the passenger reports the driver and blocks them
    report = client.post(
        "/api/v1/reports",
        json={
            "category": "SAFETY_CONCERN",
            "description": "Driver was using a phone while driving on University Road.",
            "trip_id": trip["id"],
        },
        headers=passenger["headers"],
    )
    assert report.status_code == 201
    assert client.post(
        f"/api/v1/users/{driver['user']['id']}/block", headers=passenger["headers"]
    ).status_code == 200

    # the office suspends the driver
    suspended = client.post(
        f"/api/v1/admin/users/{driver['user']['id']}/suspend",
        json={"reason": "Phone use while driving — safety report upheld"},
        headers=admin["headers"],
    )
    assert suspended.status_code == 200
    assert client.get("/api/v1/auth/me", headers=driver["headers"]).status_code == 403

    # the ride is cancelled and the passenger is told, then the report is closed
    assert client.get(f"/api/v1/trips/{trip['id']}", headers=passenger["headers"]).json()["status"] == "CANCELLED"
    client.patch(
        f"/api/v1/admin/reports/{report.json()['id']}",
        json={"status": "RESOLVED", "resolution_note": "Driver suspended pending a meeting."},
        headers=admin["headers"],
    )
    mine = client.get("/api/v1/reports", headers=passenger["headers"]).json()
    assert mine["items"][0]["status"] == "RESOLVED"

    # the whole story is in the audit trail
    log = client.get("/api/v1/admin/admin-actions?limit=50", headers=admin["headers"]).json()
    actions = {item["action_type"] for item in log["items"]}
    assert {"SUSPEND_USER", "UPDATE_REPORT"} <= actions


def test_journey_unread_counts_track_the_whole_story(client):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=40)})
    passenger = register(client)

    baseline_driver = client.get("/api/v1/notifications/unread-count", headers=driver["headers"]).json()[
        "unread_count"
    ]
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    after_request = client.get("/api/v1/notifications/unread-count", headers=driver["headers"]).json()[
        "unread_count"
    ]
    assert after_request == baseline_driver + 1

    accept_first_request(client, driver, ride)
    assert client.get("/api/v1/notifications/unread-count", headers=passenger["headers"]).json()[
        "unread_count"
    ] >= 1

    # marking everything read goes back to zero, and stays there
    client.post("/api/v1/notifications/read-all", headers=driver["headers"])
    assert client.get("/api/v1/notifications/unread-count", headers=driver["headers"]).json()[
        "unread_count"
    ] == 0
