"""Shared test helpers for the ride-system suites."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def student_id_for(suffix: str) -> str:
    """Valid SSUET student ID (YYYYF-Bcs-NNN style) that is unique per suffix.

    The programme part carries six letters derived from the hex suffix, so
    the (role, university_id) unique constraint never collides in tests.
    """
    programme = "".join(chr(ord("a") + int(ch, 16)) for ch in suffix[:6])
    return f"2023F-{programme.capitalize()}-301"


def register(client, **overrides) -> dict:
    """Register a verified student (trusted university domain) and return the payload."""
    suffix = uuid.uuid4().hex[:6]
    payload = {
        "full_name": f"Test User {suffix}",
        "email": f"user{suffix}@ssuet.edu.pk",
        "password": "Password123",
        "phone": f"+92300{suffix[:7].rjust(7, '1')}",
        "role": "STUDENT",
        "university_id": student_id_for(suffix),
        "department": "Computer Science",
        "semester": 5,
        "home_area": "Gulshan-e-Iqbal",
    }
    payload.update(overrides)
    if payload.get("role") == "TEACHER":
        # semester/degree belong to students only — sending them is a 422 by design
        payload.pop("semester", None)
        payload.pop("degree_programme", None)
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    body["headers"] = auth_header(body["access_token"])
    return body


def create_vehicle(client, headers, **overrides) -> dict:
    suffix = uuid.uuid4().hex[:5].upper()
    payload = {
        "vehicle_type": "CAR",
        "make_and_model": "Toyota Corolla 2019",
        "color": "White",
        "registration_number": f"TST-{suffix}",
        "passenger_capacity": 1,
    }
    payload.update(overrides)
    response = client.post("/api/v1/vehicles", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def future(hours: int = 5) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def ride_payload(vehicle_id: str | None = None, **overrides) -> dict:
    payload = {
        "direction": "HOME_TO_UNIVERSITY",
        "pickup_area": "Gulshan-e-Iqbal",
        "pickup_point": {"latitude": 24.92, "longitude": 67.09},
        "departure_at": future(5),
        "fuel_preference": "FREE",
        "contribution_type": "NONE",
        "note": "Leaving on time.",
    }
    payload["vehicle_id"] = overrides.pop("vehicle_id", vehicle_id)
    payload.update(overrides)
    return payload


def publish(client, headers, vehicle_id: str, **overrides) -> dict:
    response = client.post("/api/v1/rides", json=ride_payload(vehicle_id, **overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def passenger_setup(client, ride_overrides: dict | None = None, **user_overrides):
    """A verified member with a car and one published journey.

    `user_overrides` shape the account, `ride_overrides` shape the published ride
    (e.g. a departure time that opens a lifecycle window in the trip tests).
    """
    driver = register(client, **user_overrides)
    vehicle = create_vehicle(client, driver["headers"])
    ride = publish(client, driver["headers"], vehicle["id"], **(ride_overrides or {}))
    return driver, vehicle, ride
