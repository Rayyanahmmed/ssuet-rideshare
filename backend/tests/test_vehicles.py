"""Phase 3 — vehicle registration & moderation rules (§5)."""

from __future__ import annotations

from tests.helpers import create_vehicle, publish, register


def test_register_vehicle_starts_pending(client):
    user = register(client)
    vehicle = create_vehicle(
        client, user["headers"], registration_number="abc 1234", make_and_model="Honda Civic"
    )
    assert vehicle["status"] == "PENDING"          # admin verification required
    assert vehicle["registration_number"] == "ABC-1234"
    assert vehicle["is_primary"] is True


def test_only_one_primary_vehicle(client):
    user = register(client)
    first = create_vehicle(client, user["headers"])
    second = create_vehicle(client, user["headers"], vehicle_type="BIKE", make_and_model="CD 70")
    listed = client.get("/api/v1/vehicles", headers=user["headers"]).json()
    primaries = [v for v in listed if v["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["id"] == second["id"]
    assert first["is_primary"] is True  # response snapshot at creation time


def test_duplicate_registration_number_is_rejected(client):
    owner = register(client)
    create_vehicle(client, owner["headers"], registration_number="DUP-999")
    other = register(client)
    response = client.post(
        "/api/v1/vehicles",
        json={
            "vehicle_type": "CAR",
            "make_and_model": "Suzuki Alto",
            "color": "Silver",
            "registration_number": "DUP 999",
            "passenger_capacity": 1,
        },
        headers=other["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["registration_number"] == "already registered"


def test_capacity_out_of_range_is_rejected(client):
    user = register(client)
    response = client.post(
        "/api/v1/vehicles",
        json={
            "vehicle_type": "CAR",
            "make_and_model": "Corolla",
            "color": "White",
            "registration_number": "CAP-111",
            "passenger_capacity": 12,
        },
        headers=user["headers"],
    )
    assert response.status_code == 422


def test_update_vehicle_resets_verification(client, db):
    user = register(client)
    vehicle = create_vehicle(client, user["headers"])
    response = client.patch(
        f"/api/v1/vehicles/{vehicle['id']}",
        json={"color": "Black", "registration_number": "new-555"},
        headers=user["headers"],
    )
    assert response.status_code == 200
    assert response.json()["registration_number"] == "NEW-555"
    assert response.json()["status"] == "PENDING"


def test_cannot_touch_another_members_vehicle(client):
    owner = register(client)
    vehicle = create_vehicle(client, owner["headers"])
    intruder = register(client)

    assert (
        client.patch(
            f"/api/v1/vehicles/{vehicle['id']}", json={"color": "Red"}, headers=intruder["headers"]
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/vehicles/{vehicle['id']}", headers=intruder["headers"]).status_code == 403
    )


def test_vehicle_in_use_cannot_be_deleted(client):
    driver = register(client)
    vehicle = create_vehicle(client, driver["headers"])
    publish(client, driver["headers"], vehicle["id"])

    response = client.delete(f"/api/v1/vehicles/{vehicle['id']}", headers=driver["headers"])
    assert response.status_code == 422


def test_delete_vehicle_when_unused(client):
    user = register(client)
    vehicle = create_vehicle(client, user["headers"])
    assert client.delete(f"/api/v1/vehicles/{vehicle['id']}", headers=user["headers"]).status_code == 200
    assert client.get("/api/v1/vehicles", headers=user["headers"]).json() == []
