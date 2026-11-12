"""Phase 3 — publishing, discovery, privacy and editing (§7, §8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import create_vehicle, future, publish, register, ride_payload


# ------------------------------------------------------------------ publish
def test_publish_forces_the_campus_end(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    assert ride["destination_area"] == "SSUET, University Road, Karachi"
    assert ride["pickup_area"] == "Gulshan-e-Iqbal"
    assert ride["status"] == "OPEN"
    assert ride["seats_remaining"] == 1
    assert ride["fuel_preference"] == "FREE"
    assert ride["contribution"] is None
    # driver sees their own exact location
    assert ride["pickup_point"] == {"latitude": 24.92, "longitude": 67.09}


def test_return_journey_starts_at_campus(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(
        client,
        driver["headers"],
        vehicle["id"],
        direction="UNIVERSITY_TO_HOME",
        pickup_area=None,
        pickup_point=None,
        destination_area="North Nazimabad",
        destination_point={"latitude": 24.94, "longitude": 67.04},
    )
    assert ride["pickup_area"] == "SSUET, University Road, Karachi"
    assert ride["destination_area"] == "North Nazimabad"


def test_university_bound_ride_requires_a_pickup(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    response = client.post(
        "/api/v1/rides",
        json=ride_payload(vehicle["id"], pickup_area=None, pickup_point=None),
        headers=driver["headers"],
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"departure_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}, "past departure"),
        ({"departure_at": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat()}, "too far ahead"),
        ({"available_seats": 3}, "more than the allowed seats"),
        ({"fuel_preference": "FREE", "contribution_type": "FIXED", "contribution_amount": 200}, "free ride asking money"),
        ({"fuel_preference": "SHARE_FUEL", "contribution_type": "NONE"}, "share fuel without a type"),
        ({"fuel_preference": "SHARE_FUEL", "contribution_type": "NEGOTIABLE", "contribution_amount": 100}, "negotiable with an amount"),
        ({"vehicle_id": str(uuid.uuid4())}, "unknown vehicle"),
        ({"fuel_preference": "SHARE_FUEL", "contribution_type": "FIXED"}, "fixed share without an amount"),
        ({"fuel_preference": "SHARE_FUEL", "contribution_type": "EXPECTED", "contribution_amount": 0}, "expected share of zero"),
    ],
)
def test_publish_validation(client, overrides, reason):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    # merge so an overriding vehicle_id replaces the driver's own car
    payload = ride_payload(**{"vehicle_id": vehicle["id"], **overrides})
    response = client.post("/api/v1/rides", json=payload, headers=driver["headers"])
    # unknown/foreign vehicle → 404/403, rule violations → 422
    assert response.status_code in (403, 404, 422), f"{reason} should be rejected"


def test_share_fuel_ride_keeps_the_contribution(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(
        client,
        driver["headers"],
        vehicle["id"],
        fuel_preference="SHARE_FUEL",
        contribution_type="FIXED",
        contribution_amount=150,
        contribution_note="Cash on the way",
    )
    assert ride["contribution"] == {"type": "FIXED", "amount": 150.0, "note": "Cash on the way"}


def test_cannot_publish_with_someone_elses_vehicle(client):
    owner = register(client)
    vehicle = create_vehicle(client, owner["headers"])
    other = register(client)
    response = client.post(
        "/api/v1/rides", json=ride_payload(vehicle["id"]), headers=other["headers"]
    )
    assert response.status_code == 403


def test_unverified_member_cannot_publish(client):
    user = register(client, email=f"unverified{uuid.uuid4().hex[:5]}@gmail.com")
    vehicle = create_vehicle(client, user["headers"])
    response = client.post("/api/v1/rides", json=ride_payload(vehicle["id"]), headers=user["headers"])
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason_code"] == "ACCOUNT_NOT_VERIFIED"


def test_rejected_vehicle_cannot_be_used(client, db):
    from app.models import Vehicle

    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    stored = db.get(Vehicle, uuid.UUID(vehicle["id"]))
    stored.status = "REJECTED"
    db.commit()

    response = client.post(
        "/api/v1/rides", json=ride_payload(vehicle["id"]), headers=driver["headers"]
    )
    assert response.status_code == 422


def test_driver_cannot_double_book_themselves(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"], departure_at=future(5))

    response = client.post(
        "/api/v1/rides",
        json=ride_payload(vehicle["id"], departure_at=future(5)),
        headers=driver["headers"],
    )
    assert response.status_code == 409


# ---------------------------------------------------------------- discovery
def test_explore_lists_only_open_future_rides(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    open_ride = publish(client, driver["headers"], vehicle["id"])

    viewer = register(client)
    feed = client.get("/api/v1/rides", headers=viewer["headers"]).json()
    ids = [item["id"] for item in feed["items"]]
    assert open_ride["id"] in ids
    assert all(item["status"] == "OPEN" for item in feed["items"])


def test_explore_anonymous_access_is_allowed_but_private_data_is_not(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"])

    feed = client.get("/api/v1/rides").json()
    assert feed["count"] >= 1
    card = feed["items"][0]
    assert card["pickup_point"] is None      # exact location hidden
    assert card["can_request"] is False      # not signed in


@pytest.mark.parametrize(
    "query,expected_field",
    [
        ("direction=UNIVERSITY_TO_HOME", "direction"),
        ("vehicle_type=BIKE", "vehicle_type"),
        ("fuel_preference=SHARE_FUEL", "fuel_preference"),
    ],
)
def test_explore_filters(client, query, expected_field):
    car_driver = register(client)
    car = create_vehicle(client, car_driver["headers"])
    publish(client, car_driver["headers"], car["id"], fuel_preference="FREE")

    bike_driver = register(client)
    bike = create_vehicle(client, bike_driver["headers"], vehicle_type="BIKE", make_and_model="CD 70")
    publish(
        client,
        bike_driver["headers"],
        bike["id"],
        direction="UNIVERSITY_TO_HOME",
        pickup_area=None,
        pickup_point=None,
        destination_area="Malir",
        destination_point={"latitude": 24.89, "longitude": 67.20},
        fuel_preference="SHARE_FUEL",
        contribution_type="FIXED",
        contribution_amount=80,
    )

    feed = client.get(f"/api/v1/rides?{query}").json()
    assert feed["count"] >= 1
    expected = "BIKE" if expected_field == "vehicle_type" else (
        "SHARE_FUEL" if expected_field == "fuel_preference" else "UNIVERSITY_TO_HOME"
    )
    for item in feed["items"]:
        if expected_field == "vehicle_type":
            assert item["vehicle"]["vehicle_type"] == expected
        else:
            assert item[expected_field] == expected


def test_explore_area_search_is_case_insensitive(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"], pickup_area="Gulistan-e-Johar")

    found = client.get("/api/v1/rides?area=gulistan").json()
    assert found["count"] >= 1
    assert all("gulistan" in item["pickup_area"].lower() for item in found["items"])


def test_explore_nearby_radius_filter(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"], pickup_point={"latitude": 24.92, "longitude": 67.09})

    near = client.get("/api/v1/rides?lat=24.92&lng=67.09&radius_km=3").json()
    far = client.get("/api/v1/rides?lat=24.60&lng=66.80&radius_km=3").json()
    assert near["count"] >= 1
    assert far["count"] == 0


def test_explore_departure_window_and_dates(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    early = publish(client, driver["headers"], vehicle["id"], departure_at=future(3))

    windowed = client.get(
        "/api/v1/rides",
        params={
            "departure_after": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "departure_before": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        },
    ).json()
    assert [item["id"] for item in windowed["items"]] == [early["id"]]


def test_exclude_own_rides(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"])

    own = client.get("/api/v1/rides?exclude_own=true", headers=driver["headers"]).json()
    assert own["count"] == 0


def test_cursor_pagination_walks_the_feed(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    for hours in (4, 6):
        publish(client, driver["headers"], vehicle["id"], departure_at=future(hours))
    # a second driver so the same-driver window rule does not interfere
    second = register(client)
    second_vehicle = create_vehicle(client, second["headers"])
    publish(client, second["headers"], second_vehicle["id"], departure_at=future(8))

    first_page = client.get("/api/v1/rides?limit=2").json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"]

    second_page = client.get(f"/api/v1/rides?limit=2&cursor={first_page['next_cursor']}").json()
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None
    assert {item["id"] for item in first_page["items"]} & {item["id"] for item in second_page["items"]} == set()


def test_invalid_cursor_is_a_validation_error(client):
    response = client.get("/api/v1/rides?cursor=not-a-cursor")
    assert response.status_code == 422


# ------------------------------------------------------------------ details
def test_stranger_sees_area_but_not_exact_location_or_phone(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    stranger = register(client)
    detail = client.get(f"/api/v1/rides/{ride['id']}", headers=stranger["headers"]).json()
    assert detail["pickup_area"] == "Gulshan-e-Iqbal"
    assert detail["pickup_point"] is None
    assert detail["destination_point"] is None
    assert detail["driver_phone"] is None
    assert detail["driver"]["verification_status"] == "VERIFIED"


def test_driver_sees_own_location_and_phone(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    detail = client.get(f"/api/v1/rides/{ride['id']}", headers=driver["headers"]).json()
    assert detail["pickup_point"] is not None
    assert detail["driver_phone"] is not None
    assert detail["is_own_ride"] is True
    assert detail["can_request"] is False


def test_unknown_ride_is_404(client):
    viewer = register(client)
    assert client.get(f"/api/v1/rides/{uuid.uuid4()}", headers=viewer["headers"]).status_code == 404


# ------------------------------------------------------------ edit / cancel
def test_edit_while_open(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    response = client.patch(
        f"/api/v1/rides/{ride['id']}",
        json={"note": "Leaving from the main gate", "fuel_preference": "SHARE_FUEL", "contribution_type": "EXPECTED", "contribution_amount": 120},
        headers=driver["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["note"] == "Leaving from the main gate"
    assert body["contribution"]["amount"] == 120.0


def test_edit_after_matching_is_rejected(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    passenger = register(client)
    request = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={"message": "Salam"}, headers=passenger["headers"]
    ).json()
    client.post(f"/api/v1/requests/{request['id']}/accept", headers=driver["headers"])

    response = client.patch(f"/api/v1/rides/{ride['id']}", json={"note": "changed"}, headers=driver["headers"])
    assert response.status_code == 409


def test_only_the_driver_can_cancel(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"])

    other = register(client)
    assert (
        client.post(
            f"/api/v1/rides/{ride['id']}/cancel", json={"reason": "x"}, headers=other["headers"]
        ).status_code
        == 403
    )

    cancelled = client.post(
        f"/api/v1/rides/{ride['id']}/cancel",
        json={"reason": "Car broke down"},
        headers=driver["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    # gone from discovery
    assert client.get("/api/v1/rides").json()["count"] == 0


def test_my_rides_list_and_status_filter(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    open_ride = publish(client, driver["headers"], vehicle["id"])

    mine = client.get("/api/v1/rides/mine", headers=driver["headers"]).json()
    assert [ride["id"] for ride in mine] == [open_ride["id"]]

    client.post(f"/api/v1/rides/{open_ride['id']}/cancel", json={}, headers=driver["headers"])
    open_only = client.get("/api/v1/rides/mine?status=OPEN", headers=driver["headers"]).json()
    cancelled_only = client.get("/api/v1/rides/mine?status=CANCELLED", headers=driver["headers"]).json()
    assert open_only == []
    assert len(cancelled_only) == 1


def test_editing_a_ride_to_fixed_share_needs_an_amount(client):
    """A ride cannot be switched to a fixed or expected share without an amount (edit path)."""
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(
        client,
        driver["headers"],
        vehicle["id"],
        fuel_preference="SHARE_FUEL",
        contribution_type="NEGOTIABLE",
    )
    assert ride["contribution"]["type"] == "NEGOTIABLE"

    missing = client.patch(
        f"/api/v1/rides/{ride['id']}",
        json={"contribution_type": "FIXED"},
        headers=driver["headers"],
    )
    assert missing.status_code == 422, missing.text

    fixed = client.patch(
        f"/api/v1/rides/{ride['id']}",
        json={"contribution_type": "FIXED", "contribution_amount": 180},
        headers=driver["headers"],
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["contribution"] == {"type": "FIXED", "amount": 180.0, "note": None}
