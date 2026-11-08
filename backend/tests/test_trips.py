"""Phase 4 — trip lifecycle tests (§10).

Covers start / complete / cancel / no-show, the state-machine guards, seat reuse
after a passenger cancels, trip-level privacy, and the two clock-driven
maintenance jobs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import create_vehicle, passenger_setup, publish, register

TRIPS = "/api/v1/trips"


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client, *, depart_in_minutes: int = 300, **ride_overrides):
    """Driver + passenger with an accepted request → CONFIRMED trip."""
    departure = iso(minutes=depart_in_minutes)
    driver, vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": departure, **ride_overrides}
    )
    passenger = register(client)
    response = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={"message": "Salam!"}, headers=passenger["headers"]
    )
    assert response.status_code == 201, response.text
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"])
    assert trip.status_code == 200, trip.text
    return driver, passenger, ride, trip.json(), request_id


def shift_departure(db, ride_id: str, **delta):
    """Move a ride's departure into the past so lifecycle windows open up."""
    from app.models.ride import Ride

    ride = db.get(Ride, uuid.UUID(str(ride_id)))
    new_departure = datetime.now(timezone.utc) + timedelta(**delta)
    ride.departure_at = new_departure
    ride.departure_date = new_departure
    db.commit()
    db.refresh(ride)


# ------------------------------------------------------------------ discovery
def test_trip_created_on_accept_is_visible_to_both_sides(client):
    driver, passenger, _ride, trip, _req = matched_trip(client)

    assert trip["status"] == "CONFIRMED"
    assert trip["my_role"] == "DRIVER"

    driver_trips = client.get(f"{TRIPS}/mine", headers=driver["headers"]).json()
    passenger_trips = client.get(f"{TRIPS}/mine", headers=passenger["headers"]).json()
    assert driver_trips["count"] == 1 and passenger_trips["count"] == 1
    assert passenger_trips["items"][0]["my_role"] == "PASSENGER"


def test_trip_role_filter_and_upcoming_flag(client):
    driver, _passenger, _ride, _trip, _req = matched_trip(client)

    as_passenger = client.get(f"{TRIPS}/mine?role=PASSENGER", headers=driver["headers"]).json()
    assert as_passenger["count"] == 0

    upcoming = client.get(f"{TRIPS}/mine?upcoming=true", headers=driver["headers"]).json()
    assert upcoming["count"] == 1
    history = client.get(f"{TRIPS}/mine?upcoming=false", headers=driver["headers"]).json()
    assert history["count"] == 0


def test_invalid_role_filter_is_rejected(client):
    driver, *_ = matched_trip(client)
    response = client.get(f"{TRIPS}/mine?role=CAPTAIN", headers=driver["headers"])
    assert response.status_code == 422


def test_third_member_cannot_open_the_trip(client):
    _driver, _passenger, _ride, trip, _req = matched_trip(client)
    outsider = register(client)
    response = client.get(f"{TRIPS}/{trip['id']}", headers=outsider["headers"])
    assert response.status_code == 403


def test_trip_requires_authentication(client):
    _driver, _passenger, _ride, trip, _req = matched_trip(client)
    assert client.get(f"{TRIPS}/{trip['id']}").status_code == 401
    assert client.get(f"{TRIPS}/mine").status_code == 401


def test_unknown_trip_is_404(client):
    user = register(client)
    response = client.get(f"{TRIPS}/00000000-0000-0000-0000-000000000000", headers=user["headers"])
    assert response.status_code == 404


# ---------------------------------------------------------------------- start
def test_driver_starts_journey(client):
    driver, passenger, ride, trip, _req = matched_trip(client)

    response = client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["started_at"] is not None
    assert body["can_complete"] is True

    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "IN_PROGRESS"

    # the passenger is told the journey began
    notifications = client.get("/api/v1/notifications", headers=passenger["headers"])
    if notifications.status_code == 200:  # pragma: no cover - Phase 5 endpoint
        assert any(n["type"] == "TRIP_STARTED" for n in notifications.json()["items"])


def test_passenger_cannot_start_journey(client):
    _driver, passenger, _ride, trip, _req = matched_trip(client)
    response = client.post(f"{TRIPS}/{trip['id']}/start", headers=passenger["headers"])
    assert response.status_code == 403


def test_journey_cannot_start_twice(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client)
    assert client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"]).status_code == 200
    second = client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    assert second.status_code == 409


def test_journey_cannot_start_too_early(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client, depart_in_minutes=20 * 60)
    detail = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    assert detail["can_start"] is False

    response = client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    assert response.status_code == 409
    assert "cannot be started yet" in response.json()["error"]["message"].lower()


# ------------------------------------------------------------------- complete
def test_completion_needs_both_sides(client):
    driver, passenger, ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])

    first = client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    assert first.status_code == 200
    assert first.json()["status"] == "IN_PROGRESS"
    assert first.json()["driver_confirmed_complete"] is True

    passenger_view = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert passenger_view["awaiting_my_confirmation"] is True

    second = client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"])
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "COMPLETED"
    assert body["completed_at"] is not None
    assert body["can_review"] is True

    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "COMPLETED"


def test_completion_increments_both_member_records(client):
    driver, passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"])

    driver_me = client.get("/api/v1/auth/me", headers=driver["headers"]).json()
    passenger_me = client.get("/api/v1/auth/me", headers=passenger["headers"]).json()
    assert driver_me["completed_trips_count"] >= 1
    assert passenger_me["completed_trips_count"] >= 1


def test_cannot_complete_before_start(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client)
    response = client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    assert response.status_code == 409
    assert "in progress" in response.json()["error"]["message"].lower()


def test_same_side_cannot_confirm_twice(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    assert client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"]).status_code == 200
    again = client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    assert again.status_code == 409


def test_completed_trip_is_terminal(client):
    driver, passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"])

    assert client.post(f"{TRIPS}/{trip['id']}/cancel", headers=driver["headers"]).status_code == 409
    assert client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"]).status_code == 409
    assert client.post(f"{TRIPS}/{trip['id']}/no-show", headers=driver["headers"]).status_code == 409


# --------------------------------------------------------------------- cancel
def test_passenger_cancel_reopens_the_ride(client):
    driver, passenger, ride, trip, request_id = matched_trip(client)

    response = client.post(
        f"{TRIPS}/{trip['id']}/cancel",
        json={"reason": "Change of plans"},
        headers=passenger["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancellation_reason"] == "Change of plans"

    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "OPEN"
    assert ride_after["seats_remaining"] == 1

    # the seat is genuinely reusable: a new passenger can be accepted
    replacement = register(client)
    new_request = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={}, headers=replacement["headers"]
    )
    assert new_request.status_code == 201
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    new_request_id = next(
        item["id"] for item in inbox if item["ride_id"] == ride["id"] and item["status"] == "PENDING"
    )
    accepted = client.post(
        f"/api/v1/requests/{new_request_id}/accept", headers=driver["headers"]
    )
    assert accepted.status_code == 200
    assert accepted.json()["passenger"]["id"] == replacement["user"]["id"]
    assert accepted.json()["id"] != trip["id"]


def test_driver_cancel_kills_the_ride(client):
    driver, passenger, ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])

    response = client.post(
        f"{TRIPS}/{trip['id']}/cancel", json={"reason": "Car broke down"}, headers=driver["headers"]
    )
    assert response.status_code == 200
    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "CANCELLED"

    # passenger keeps the record in history
    history = client.get(f"{TRIPS}/mine?upcoming=false", headers=passenger["headers"]).json()
    assert history["count"] == 1
    assert history["items"][0]["status"] == "CANCELLED"


def test_passenger_cannot_cancel_after_start(client):
    driver, passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    response = client.post(f"{TRIPS}/{trip['id']}/cancel", headers=passenger["headers"])
    assert response.status_code == 409
    assert "already started" in response.json()["error"]["message"].lower()


def test_outsider_cannot_cancel(client):
    _driver, _passenger, _ride, trip, _req = matched_trip(client)
    outsider = register(client)
    response = client.post(f"{TRIPS}/{trip['id']}/cancel", headers=outsider["headers"])
    assert response.status_code == 403


# -------------------------------------------------------------------- no-show
def test_no_show_before_departure_frees_the_seat(client):
    driver, passenger, ride, trip, _req = matched_trip(client, depart_in_minutes=20)

    response = client.post(
        f"{TRIPS}/{trip['id']}/no-show", json={"reason": "Not at the meeting point"}, headers=driver["headers"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "NO_SHOW"
    assert response.json()["can_complete"] is True  # driver can still close the ride

    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "OPEN"
    assert ride_after["seats_remaining"] == 1

    passenger_history = client.get(f"{TRIPS}/mine?upcoming=false", headers=passenger["headers"]).json()
    assert passenger_history["items"][0]["status"] == "NO_SHOW"


def test_only_driver_can_mark_no_show(client):
    _driver, passenger, _ride, trip, _req = matched_trip(client, depart_in_minutes=20)
    response = client.post(f"{TRIPS}/{trip['id']}/no-show", headers=passenger["headers"])
    assert response.status_code == 403


def test_no_show_too_early_is_rejected(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client, depart_in_minutes=180)
    response = client.post(f"{TRIPS}/{trip['id']}/no-show", headers=driver["headers"])
    assert response.status_code == 409
    assert "30 minutes" in response.json()["error"]["message"]


def test_no_show_after_departure_completes_the_ride(client, db):
    driver, _passenger, ride, trip, _req = matched_trip(client, depart_in_minutes=30)
    shift_departure(db, ride["id"], minutes=-5)

    response = client.post(f"{TRIPS}/{trip['id']}/no-show", headers=driver["headers"])
    assert response.status_code == 200
    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "COMPLETED"


def test_driver_completes_after_no_show(client):
    driver, _passenger, _ride, trip, _req = matched_trip(client, depart_in_minutes=20)
    client.post(f"{TRIPS}/{trip['id']}/no-show", headers=driver["headers"])

    response = client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == "NO_SHOW"


# ------------------------------------------------------------------ privacy
def test_trip_shares_contact_only_with_participants(client):
    driver, passenger, _ride, trip, _req = matched_trip(client)

    driver_view = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    passenger_view = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert driver_view["counterpart"]["phone"] == passenger_view["passenger_phone"]
    assert passenger_view["counterpart"]["phone"] == driver_view["driver_phone"]

    outside = client.get(f"/api/v1/rides/{_ride['id']}", headers=register(client)["headers"]).json()
    assert outside["pickup_point"] is None
    assert outside["my_trip_id"] is None


# -------------------------------------------------------------- maintenance
def test_stale_open_ride_expires_with_its_requests(client, db):
    from app.services.maintenance_service import expire_stale_rides

    driver, vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=90)})
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])

    shift_departure(db, ride["id"], minutes=-120)
    result = expire_stale_rides(db)
    assert result.expired_rides == 1
    assert result.withdrawn_requests == 1

    after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert after["status"] == "EXPIRED"

    mine = client.get("/api/v1/requests/mine", headers=passenger["headers"]).json()
    assert mine["items"][0]["status"] == "CANCELLED"


def test_fresh_ride_is_not_expired(client, db):
    from app.services.maintenance_service import expire_stale_rides

    passenger_setup(client)
    assert expire_stale_rides(db).expired_rides == 0


def test_matched_but_never_started_ride_expires(client, db):
    from app.services.maintenance_service import expire_stale_rides

    driver, passenger, ride, trip, _req = matched_trip(client, depart_in_minutes=120)
    shift_departure(db, ride["id"], minutes=-180)

    result = expire_stale_rides(db)
    assert result.expired_rides == 1
    assert result.abandoned_trips == 1

    history = client.get(f"{TRIPS}/mine?upcoming=false", headers=passenger["headers"]).json()
    assert history["items"][0]["status"] == "CANCELLED"


def test_stale_trip_is_auto_completed_when_one_side_confirmed(client, db):
    from app.services.maintenance_service import auto_complete_stale_trips

    driver, passenger, ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])

    # pretend the journey started 30 hours ago
    from app.models.trip import Trip

    row = db.get(Trip, uuid.UUID(str(trip["id"])))
    row.started_at = datetime.now(timezone.utc) - timedelta(hours=30)
    db.commit()

    result = auto_complete_stale_trips(db)
    assert result.auto_completed_trips == 1

    final = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert final["status"] == "COMPLETED"
    assert final["passenger_confirmed_complete"] is True
    ride_after = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert ride_after["status"] == "COMPLETED"


def test_recent_trip_is_not_auto_completed(client, db):
    from app.services.maintenance_service import auto_complete_stale_trips

    driver, _passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])

    assert auto_complete_stale_trips(db).auto_completed_trips == 0


def test_trip_without_any_confirmation_is_left_alone(client, db):
    from app.models.trip import Trip
    from app.services.maintenance_service import auto_complete_stale_trips

    driver, _passenger, _ride, trip, _req = matched_trip(client)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])

    row = db.get(Trip, uuid.UUID(str(trip["id"])))
    row.started_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db.commit()

    assert auto_complete_stale_trips(db).auto_completed_trips == 0
    assert client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()["status"] == "IN_PROGRESS"


@pytest.mark.parametrize("action", ["start", "complete", "cancel", "no-show"])
def test_actions_on_missing_trip_are_404(client, action):
    user = register(client)
    response = client.post(
        f"{TRIPS}/00000000-0000-0000-0000-000000000000/{action}", headers=user["headers"]
    )
    assert response.status_code == 404
