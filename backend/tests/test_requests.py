"""Phase 3 — ride requests and the one-passenger invariant (§9, §23)."""

from __future__ import annotations

import threading
import uuid

import pytest

from app.core.exceptions import SeatUnavailableError
from app.services import request_service
from tests.helpers import create_vehicle, publish, register


def setup_ride(client):
    """A driver with a published journey, plus three verified prospective passengers."""
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])
    passengers = [register(client) for _ in range(3)]
    return driver, vehicle, ride, passengers


def ask(client, passenger, ride_id, message="Salam, can I join?"):
    return client.post(
        f"/api/v1/rides/{ride_id}/requests", json={"message": message}, headers=passenger["headers"]
    )


# ------------------------------------------------------------- requesting
def test_request_to_join_creates_a_pending_request_and_notifies_driver(client, db):
    from sqlalchemy import select

    from app.models import Notification

    driver, _, ride, passengers = setup_ride(client)
    response = ask(client, passengers[0], ride["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["message"] == "Salam, can I join?"

    notifications = db.scalars(
        select(Notification).where(Notification.user_id == uuid.UUID(driver["user"]["id"]))
    ).all()
    assert any(n.type.value == "RIDE_REQUEST_RECEIVED" for n in notifications)


def test_cannot_request_your_own_ride(client):
    driver, _, ride, _ = setup_ride(client)
    response = ask(client, driver, ride["id"])
    assert response.status_code == 422


def test_duplicate_pending_request_is_rejected(client):
    _, _, ride, passengers = setup_ride(client)
    assert ask(client, passengers[0], ride["id"]).status_code == 201
    second = ask(client, passengers[0], ride["id"], message="Still interested")
    assert second.status_code == 409


def test_unverified_member_cannot_request(client):
    _, _, ride, _ = setup_ride(client)
    unverified = register(client, email=f"noverify{uuid.uuid4().hex[:6]}@gmail.com")
    response = ask(client, unverified, ride["id"])
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason_code"] == "ACCOUNT_NOT_VERIFIED"


def test_blocked_member_cannot_request(client):
    driver, _, ride, passengers = setup_ride(client)
    passenger = passengers[0]
    client.post(
        f"/api/v1/users/{driver['user']['id']}/block", headers=passenger["headers"]
    )
    response = ask(client, passenger, ride["id"])
    assert response.status_code == 403


def test_request_on_matched_ride_is_unavailable(client):
    driver, _, ride, passengers = setup_ride(client)
    first = ask(client, passengers[0], ride["id"]).json()
    client.post(f"/api/v1/requests/{first['id']}/accept", headers=driver["headers"])

    response = ask(client, passengers[1], ride["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RIDE_NOT_AVAILABLE"


def test_passenger_can_withdraw_a_pending_request(client):
    _, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()

    mine = client.get("/api/v1/requests/mine", headers=passengers[0]["headers"]).json()
    assert mine["count"] == 1
    assert mine["items"][0]["ride"]["pickup_area"] == "Gulshan-e-Iqbal"

    cancelled = client.post(
        f"/api/v1/requests/{request['id']}/cancel", headers=passengers[0]["headers"]
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_another_member_cannot_cancel_my_request(client):
    _, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()
    response = client.post(
        f"/api/v1/requests/{request['id']}/cancel", headers=passengers[1]["headers"]
    )
    assert response.status_code == 403


# ---------------------------------------------------------------- accepting
def test_accept_reserves_the_single_seat_and_opens_chat(client, db):
    from sqlalchemy import select

    from app.models import Conversation, Notification, Ride, Trip

    driver, _, ride, passengers = setup_ride(client)
    chosen = ask(client, passengers[0], ride["id"]).json()
    runner_up = ask(client, passengers[1], ride["id"]).json()

    response = client.post(f"/api/v1/requests/{chosen['id']}/accept", headers=driver["headers"])
    assert response.status_code == 200, response.text
    trip = response.json()
    assert trip["status"] == "CONFIRMED"
    assert trip["conversation_id"] is not None
    assert trip["meeting_point"] == "Gulshan-e-Iqbal"
    assert trip["meeting_location"] is not None

    stored_ride = db.get(Ride, uuid.UUID(ride["id"]))
    db.refresh(stored_ride)
    assert stored_ride.status.value == "MATCHED"
    assert stored_ride.seats_remaining == 0

    # exactly one live trip and one conversation
    trips = db.scalars(select(Trip).where(Trip.ride_id == stored_ride.id)).all()
    assert len(trips) == 1
    conversations = db.scalars(
        select(Conversation).where(Conversation.trip_id == trips[0].id)
    ).all()
    assert len(conversations) == 1

    # the other request was auto-declined with a note
    runner_up_status = client.get(
        "/api/v1/requests/inbox", headers=driver["headers"]
    ).json()
    declined = next(item for item in runner_up_status if item["id"] == runner_up["id"])
    assert declined["status"] == "REJECTED"
    assert "Another passenger" in (declined["response_note"] or "")

    # both sides were notified
    for member in (passengers[0], driver):
        notes = db.scalars(
            select(Notification).where(Notification.user_id == uuid.UUID(member["user"]["id"]))
        ).all()
        assert any(n.type.value == "RIDE_REQUEST_ACCEPTED" for n in notes)


def test_second_accept_is_rejected_with_ride_not_available(client):
    driver, _, ride, passengers = setup_ride(client)
    first = ask(client, passengers[0], ride["id"]).json()
    second = ask(client, passengers[1], ride["id"]).json()

    assert client.post(f"/api/v1/requests/{first['id']}/accept", headers=driver["headers"]).status_code == 200
    conflict = client.post(f"/api/v1/requests/{second['id']}/accept", headers=driver["headers"])
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RIDE_NOT_AVAILABLE"


def test_only_the_driver_can_accept(client):
    _, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()
    response = client.post(
        f"/api/v1/requests/{request['id']}/accept", headers=passengers[1]["headers"]
    )
    assert response.status_code == 403


def test_accepted_request_cannot_be_accepted_twice(client):
    driver, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()
    client.post(f"/api/v1/requests/{request['id']}/accept", headers=driver["headers"])
    again = client.post(f"/api/v1/requests/{request['id']}/accept", headers=driver["headers"])
    assert again.status_code == 409


def test_driver_can_reject_a_request(client, db):
    from sqlalchemy import select

    from app.models import Notification

    driver, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()

    response = client.post(
        f"/api/v1/requests/{request['id']}/reject",
        json={"message": "Sorry, seat already promised."},
        headers=driver["headers"],
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["response_note"] == "Sorry, seat already promised."

    notes = db.scalars(
        select(Notification).where(Notification.user_id == uuid.UUID(passengers[0]["user"]["id"]))
    ).all()
    assert any(n.type.value == "RIDE_REQUEST_REJECTED" for n in notes)


def test_driver_inbox_lists_requests_across_rides(client):
    driver, _, ride, passengers = setup_ride(client)
    ask(client, passengers[0], ride["id"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    assert len(inbox) == 1
    assert inbox[0]["passenger"]["full_name"] == passengers[0]["user"]["full_name"]
    # the driver sees requester trust signals, never their phone number
    assert "phone" not in inbox[0]["passenger"]


def test_passenger_cannot_read_another_rides_inbox(client):
    driver, _, ride, passengers = setup_ride(client)
    response = client.get(f"/api/v1/rides/{ride['id']}/requests", headers=passengers[0]["headers"])
    assert response.status_code == 403


def test_cancelling_the_ride_declines_pending_requests(client):
    driver, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()

    client.post(f"/api/v1/rides/{ride['id']}/cancel", json={"reason": "Engine trouble"}, headers=driver["headers"])

    mine = client.get("/api/v1/requests/mine", headers=passengers[0]["headers"]).json()
    assert mine["items"][0]["status"] == "REJECTED"
    assert "cancelled" in (mine["items"][0]["response_note"] or "").lower()


def test_accepted_passenger_sees_exact_meeting_point(client):
    driver, _, ride, passengers = setup_ride(client)
    request = ask(client, passengers[0], ride["id"]).json()
    client.post(f"/api/v1/requests/{request['id']}/accept", headers=driver["headers"])

    detail = client.get(f"/api/v1/rides/{ride['id']}", headers=passengers[0]["headers"]).json()
    assert detail["pickup_point"] == {"latitude": 24.92, "longitude": 67.09}
    assert detail["driver_phone"] is not None

    # an unrelated member still only sees the area
    outsider = client.get(f"/api/v1/rides/{ride['id']}", headers=passengers[2]["headers"]).json()
    assert outsider["pickup_point"] is None


# ------------------------------------------------------------- concurrency
def test_concurrent_accepts_reserve_exactly_one_seat(client, db):
    """Four threads accept four different requests on the same ride.

    Exactly one may win; the database's partial unique index is the last line of
    defence even if the application-level lock is bypassed.
    """
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models import Ride, Trip
    from app.models.user import User

    driver, _, ride, passengers = setup_ride(client)
    requests = [ask(client, passenger, ride["id"]).json() for passenger in passengers]
    driver_id = uuid.UUID(driver["user"]["id"])
    ride_id = uuid.UUID(ride["id"])

    results: list[str] = []
    lock = threading.Lock()

    def attempt(request_id: str) -> None:
        session = SessionLocal()
        try:
            driver_user = session.get(User, driver_id)
            request_service.accept_request(session, uuid.UUID(request_id), driver_user)
            outcome = "accepted"
        except SeatUnavailableError:
            outcome = "seat_unavailable"
        except Exception as error:  # noqa: BLE001 - recorded, then asserted
            outcome = type(error).__name__
        finally:
            session.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(request["id"],)) for request in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    accepted = results.count("accepted")
    assert accepted == 1, f"expected exactly one winner, got {results}"

    session = SessionLocal()
    try:
        trips = session.scalar(select(func.count(Trip.id)).where(Trip.ride_id == ride_id))
        stored_ride = session.get(Ride, ride_id)
        session.refresh(stored_ride)
        assert trips == 1
        assert stored_ride.seats_remaining == 0
        assert stored_ride.status.value == "MATCHED"
    finally:
        session.close()


def test_database_index_blocks_a_second_live_trip_directly(db):
    """Layers 1–2 removed on purpose: the unique partial index still refuses."""
    from sqlalchemy.exc import IntegrityError

    from app.models import RideRequest, Trip
    from app.models.enums import RideRequestStatus, RideDirection, RideStatus, VehicleType
    from tests.test_db_constraints import accept, make_ride
    from tests.conftest import make_user

    driver = make_user(db)
    p1, p2 = make_user(db), make_user(db)
    ride = make_ride(db, driver)
    accept(db, ride, p1)

    with pytest.raises(IntegrityError):
        accept(db, ride, p2)
    db.rollback()
