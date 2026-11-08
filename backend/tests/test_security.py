"""Phase 7 — security hardening: privacy & IDOR sweep (§8, §15, §26.9).

These tests are the regression net for the two promises the product makes about
data:

1. **Privacy before matching** — a stranger may see an approximate pickup area,
   never a phone number, an exact address or a home coordinate.
2. **Authorisation on every id** — knowing an id is never enough. Every endpoint
   that takes a `trip_id`, `conversation_id`, `notification_id`, `vehicle_id` or
   `request_id` re-derives the caller's relationship to that row server-side.

They are grouped here rather than next to the feature tests because they describe
one property that spans the whole API, and because a regression in any of them is
a security bug, not a feature bug.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import create_vehicle, passenger_setup, publish, register

PRIVATE_KEYS = {
    "phone",
    "email",
    "home_address",
    "home_latitude",
    "home_longitude",
    "exact_location",
    "meeting_point",
    "meeting_latitude",
    "meeting_longitude",
    "university_id",
}


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client):
    driver, vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=20)}
    )
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(
        f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]
    ).json()
    return driver, passenger, vehicle, ride, trip


def walk(node, path="$"):
    """Yield (json_path, key) pairs for every key in a nested payload."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def assert_no_private_keys(payload, allowed: set[str] | None = None):
    allowed = allowed or set()
    leaked = [
        f"{path} ({key})"
        for path, key in walk(payload)
        if key.lower() in PRIVATE_KEYS and key.lower() not in allowed
    ]
    assert not leaked, f"private fields leaked: {leaked}"


# ------------------------------------------------------------------ explore
def test_explore_feed_hides_contact_details_and_exact_coordinates(client):
    driver, _vehicle, _ride = passenger_setup(client)
    viewer = register(client)

    feed = client.get("/api/v1/rides", headers=viewer["headers"]).json()
    assert feed["items"], "the seeded ride should be visible to an unrelated member"
    assert_no_private_keys(feed)

    item = feed["items"][0]
    assert item["pickup_area"] == "Gulshan-e-Iqbal"   # approximate area only
    assert item["driver"]["rating_count"] >= 0
    assert "phone" not in item["driver"]


def test_ride_detail_hides_meeting_point_before_a_match(client):
    _driver, _vehicle, ride = passenger_setup(client)
    viewer = register(client)

    detail = client.get(f"/api/v1/rides/{ride['id']}", headers=viewer["headers"]).json()
    assert_no_private_keys(detail)
    assert detail.get("meeting_point") is None
    # the driver's phone is only released once the viewer is the matched passenger
    assert detail.get("driver_phone") in (None, "")


def test_public_profile_never_exposes_email_phone_or_home(client):
    driver, _vehicle, _ride = passenger_setup(client)
    viewer = register(client)

    profile = client.get(
        f"/api/v1/users/{driver['user']['id']}/public", headers=viewer["headers"]
    ).json()
    assert_no_private_keys(profile)
    assert profile["full_name"]
    assert "email" not in profile


def test_my_own_profile_does_expose_my_details(client):
    driver, _vehicle, _ride = passenger_setup(client)
    me = client.get("/api/v1/auth/me", headers=driver["headers"]).json()
    # it is my own data — the phone is legitimately mine
    assert me["phone"].startswith("+92")
    assert me["email"].endswith("@ssuet.edu.pk")


# --------------------------------------------------------------------- IDOR
def test_trip_is_invisible_to_non_participants(client):
    _driver, _passenger, _vehicle, _ride, trip = matched_trip(client)
    intruder = register(client)

    for method in ("get",):
        response = getattr(client, method)(f"/api/v1/trips/{trip['id']}", headers=intruder["headers"])
        assert response.status_code in (403, 404)


def test_trip_actions_require_the_right_participant(client):
    driver, passenger, _vehicle, _ride, trip = matched_trip(client)
    intruder = register(client)

    assert client.post(
        f"/api/v1/trips/{trip['id']}/start", headers=intruder["headers"]
    ).status_code in (403, 404)
    # the passenger cannot start somebody else's journey either
    assert client.post(
        f"/api/v1/trips/{trip['id']}/start", headers=passenger["headers"]
    ).status_code == 403
    # and a non-driver cannot mark a no-show
    assert client.post(
        f"/api/v1/trips/{trip['id']}/no-show",
        json={"reason": "never arrived"},
        headers=intruder["headers"],
    ).status_code in (403, 404)


def test_conversation_is_participant_only(client):
    _driver, _passenger, _vehicle, _ride, trip = matched_trip(client)
    intruder = register(client)
    conversation_id = client.get(
        f"/api/v1/trips/{trip['id']}", headers=_driver["headers"]
    ).json()["conversation_id"]
    assert conversation_id

    assert client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=intruder["headers"]
    ).status_code in (403, 404)
    assert client.get(
        f"/api/v1/chat/conversations/{conversation_id}/messages", headers=intruder["headers"]
    ).status_code in (403, 404)
    assert client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"body": "hello"},
        headers=intruder["headers"],
    ).status_code in (403, 404)


def test_notifications_are_private(client):
    owner = register(client)
    intruder = register(client)
    inbox = client.get("/api/v1/notifications", headers=owner["headers"]).json()
    notification_id = inbox["items"][0]["id"]

    assert client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=intruder["headers"]
    ).status_code == 404
    # the intruder's own inbox never contains the owner's rows
    their_ids = {
        item["id"]
        for item in client.get("/api/v1/notifications", headers=intruder["headers"]).json()["items"]
    }
    assert notification_id not in their_ids


def test_publishing_with_someone_elses_vehicle_is_refused(client):
    owner, vehicle, _ride = passenger_setup(client)
    intruder = register(client)
    response = client.post(
        "/api/v1/rides",
        json={
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "Gulshan-e-Iqbal",
            "pickup_point": {"latitude": 24.92, "longitude": 67.09},
            "departure_at": iso(hours=6),
            "fuel_preference": "FREE",
            "contribution_type": "NONE",
            "vehicle_id": vehicle["id"],
        },
        headers=intruder["headers"],
    )
    assert response.status_code in (403, 404, 422)


def test_only_the_driver_decides_on_requests(client):
    driver, _vehicle, ride = passenger_setup(client)
    passenger = register(client)
    other = register(client)
    created = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"]
    ).json()

    assert client.post(
        f"/api/v1/requests/{created['id']}/accept", headers=other["headers"]
    ).status_code in (403, 404)
    assert client.post(
        f"/api/v1/requests/{created['id']}/accept", headers=passenger["headers"]
    ).status_code in (403, 404)


def test_cannot_request_a_ride_you_published(client):
    driver, _vehicle, ride = passenger_setup(client)
    response = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={}, headers=driver["headers"]
    )
    assert response.status_code in (400, 403, 409, 422)


def test_vehicle_records_are_owner_scoped(client):
    _owner, vehicle, _ride = passenger_setup(client)
    intruder = register(client)

    assert client.delete(
        f"/api/v1/vehicles/{vehicle['id']}", headers=intruder["headers"]
    ).status_code in (403, 404)

    mine = client.get("/api/v1/vehicles", headers=intruder["headers"]).json()
    assert mine == []


# -------------------------------------------------------- account state gates
def test_suspended_account_cannot_use_the_api_after_suspension(client, admin):
    member = register(client)
    assert client.get("/api/v1/auth/me", headers=member["headers"]).status_code == 200

    client.post(
        f"/api/v1/admin/users/{member['user']['id']}/suspend",
        json={"reason": "Safety review pending"},
        headers=admin["headers"],
    )
    assert client.get("/api/v1/auth/me", headers=member["headers"]).status_code == 403
    assert client.get("/api/v1/rides", headers=member["headers"]).status_code == 403
    assert client.post(
        "/api/v1/reports",
        json={"category": "OTHER", "description": "Suspended members cannot file reports."},
        headers=member["headers"],
    ).status_code == 403


def test_garbage_and_foreign_tokens_are_rejected(client):
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    ).status_code == 401
    # a token signed for another audience/secret
    assert client.get(
        "/api/v1/trips/mine", headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.x"}
    ).status_code == 401


def test_unknown_and_malformed_ids_do_not_500(client):
    member = register(client)
    for path in (
        "/api/v1/trips/not-a-uuid",
        "/api/v1/rides/not-a-uuid",
        f"/api/v1/trips/{uuid.uuid4()}",
        f"/api/v1/rides/{uuid.uuid4()}",
        f"/api/v1/users/{uuid.uuid4()}/public",
        f"/api/v1/reviews/users/{uuid.uuid4()}",
    ):
        response = client.get(path, headers=member["headers"])
        assert response.status_code in (404, 422), (path, response.status_code)


# ------------------------------------------------------------ upload / input
@pytest.mark.parametrize(
    "field,value",
    [
        ("document_url", "javascript:alert(1)"),
        ("document_url", "not-a-url"),
    ],
)
def test_verification_document_url_must_be_http(client, field, value):
    member = register(client)
    response = client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID", "submitted_value": "SSUET-2026-999", field: value},
        headers=member["headers"],
    )
    assert response.status_code == 422


def test_route_notes_and_ride_fields_are_length_bounded(client):
    driver, vehicle, _ride = passenger_setup(client)
    response = client.post(
        "/api/v1/rides",
        json={
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "Gulshan-e-Iqbal",
            "pickup_point": {"latitude": 24.92, "longitude": 67.09},
            "departure_at": iso(hours=6),
            "fuel_preference": "FREE",
            "contribution_type": "NONE",
            "note": "x" * 1000,
            "vehicle_id": vehicle["id"],
        },
        headers=driver["headers"],
    )
    assert response.status_code == 422


def test_no_endpoint_returns_a_stack_trace(client):
    """Errors are the documented envelope, never an internal exception string."""
    member = register(client)
    responses = [
        client.get(f"/api/v1/trips/{uuid.uuid4()}", headers=member["headers"]),
        client.get("/api/v1/trips/not-a-uuid", headers=member["headers"]),
        client.post("/api/v1/reviews/trips/" + str(uuid.uuid4()), json={"rating": 9}, headers=member["headers"]),
    ]
    for response in responses:
        body = response.json()
        assert "error" in body
        assert "Traceback" not in str(body)
        assert "sqlalchemy" not in str(body).lower()
