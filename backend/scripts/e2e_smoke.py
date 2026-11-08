"""Live end-to-end smoke test over real HTTP — the journey the mobile app performs.

Unlike the pytest suite (in-process TestClient), this talks to a *running* server, so it also
proves the network path, the ASGI stack and the JSON contracts the phone depends on.

Usage (the API must be running):

    uvicorn app.main:app --host 0.0.0.0 --port 8000      # in another terminal
    .venv/bin/python scripts/e2e_smoke.py                # defaults to 127.0.0.1:8000
    .venv/bin/python scripts/e2e_smoke.py http://192.168.100.32:8000/api/v1

Exit code 0 = every check passed.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
TZ_KARACHI = timezone(timedelta(hours=5))

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        failures.append(label)
    print(f"{'PASS' if condition else 'FAIL':4}  {label:<46} {detail}")


class Member:
    """One authenticated member — a thin wrapper so calls read like the mobile API layer."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.headers: dict[str, str] = {}
        self.email = ""

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.client.get(url, headers=self.headers, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.client.post(url, headers=self.headers, **kwargs)

    def patch(self, url: str, **kwargs) -> httpx.Response:
        return self.client.patch(url, headers=self.headers, **kwargs)

    def register(self, name: str) -> None:
        suffix = uuid.uuid4().hex[:6]
        self.email = f"{name.lower()}.{suffix}@ssuet.edu.pk"
        response = self.client.post(
            "/auth/register",
            json={
                "full_name": f"{name} Tester",
                "email": self.email,
                "password": "Password123!",
                "phone": "03" + str(uuid.uuid4().int)[:9],
                "role": "STUDENT",
                "university_id": f"SSUET-{suffix}",
                "department": "Computer Science",
                "semester": 6,
                "home_area": "Gulshan-e-Iqbal",
            },
        )
        check(f"register {name}", response.status_code == 201, str(response.status_code))
        payload = response.json()
        self.headers = {"Authorization": f"Bearer {payload['access_token']}"}
        check(f"  · {name} auto-verified", payload["user"]["verification_status"] == "VERIFIED")

    def login(self) -> None:
        response = self.client.post("/auth/login", json={"email": self.email, "password": "Password123!"})
        check("POST /auth/login", response.status_code == 200, str(response.status_code))
        payload = response.json()
        self.headers = {"Authorization": f"Bearer {payload['access_token']}"}
        self.refresh_token = payload["refresh_token"]


def publish_and_complete(driver: Member, rider: Member, departure: str) -> None:
    vehicle = driver.post(
        "/vehicles",
        json={
            "vehicle_type": "CAR",
            "make_and_model": "Suzuki Alto 2021",
            "color": "White",
            "registration_number": f"E2E-{uuid.uuid4().hex[:5].upper()}",
            "passenger_capacity": 4,
            "is_primary": True,
        },
    )
    check("POST /vehicles", vehicle.status_code == 201, str(vehicle.status_code))
    vehicle_id = vehicle.json()["id"]

    ride = driver.post(
        "/rides",
        json={
            "direction": "UNIVERSITY_TO_HOME",
            "pickup_area": "SSUET Main Campus",
            "destination_area": "Gulshan-e-Iqbal",
            "departure_at": departure,
            "vehicle_id": vehicle_id,
            "pickup_point": {"latitude": 24.9410, "longitude": 67.1186},
            "destination_point": {"latitude": 24.9200, "longitude": 67.0900},
            "available_seats": 1,
            "fuel_preference": "SHARE_FUEL",
            "contribution_type": "EXPECTED",
            "contribution_amount": 150,
        },
    )
    check("POST /rides (publish)", ride.status_code == 201, f"{ride.status_code} {ride.text[:60]}")
    ride_id = ride.json()["id"]

    feed = driver.get("/rides", params={"direction": "UNIVERSITY_TO_HOME"})
    check(
        "GET /rides (feed)",
        feed.status_code == 200 and any(item["id"] == ride_id for item in feed.json().get("items", [])),
    )
    check("GET /rides/{id}", driver.get(f"/rides/{ride_id}").status_code == 200)
    check("PATCH /rides/{id}", driver.patch(f"/rides/{ride_id}", json={"note": "E2E note"}).status_code == 200)

    request = rider.post(f"/rides/{ride_id}/requests", json={"message": "E2E seat request"})
    check("POST /rides/{id}/requests (book)", request.status_code == 201, str(request.status_code))
    request_id = request.json()["id"]

    check("GET /rides/{id}/requests (owner)", driver.get(f"/rides/{ride_id}/requests").status_code == 200)
    check("GET /requests/inbox", driver.get("/requests/inbox").status_code == 200)

    accepted = driver.post(f"/requests/{request_id}/accept")
    check("POST /requests/{id}/accept → trip", accepted.status_code == 200, str(accepted.status_code))
    trip_id = accepted.json()["id"]

    check("GET /trips/mine (rider)", rider.get("/trips/mine").status_code == 200)
    check("POST /trips/{id}/start", driver.post(f"/trips/{trip_id}/start").status_code == 200)

    # Completion is deliberately two-sided: both confirmations finish the journey (§11).
    check("POST /trips/{id}/complete (driver)", driver.post(f"/trips/{trip_id}/complete").status_code == 200)
    check("POST /trips/{id}/complete (rider)", rider.post(f"/trips/{trip_id}/complete").status_code == 200)
    completed = driver.get(f"/trips/{trip_id}").json()
    check("trip reached COMPLETED", completed.get("status") == "COMPLETED", completed.get("status"))

    review = rider.post(f"/reviews/trips/{trip_id}", json={"rating": 5, "comment": "Smooth E2E journey"})
    check("POST /reviews/trips/{id}", review.status_code in (200, 201), str(review.status_code))
    check("GET /reviews/me/received", driver.get("/reviews/me/received").status_code == 200)
    check("GET /notifications (rider)", rider.get("/notifications").status_code == 200)

    late = driver.patch(f"/rides/{ride_id}", json={"note": "late edit"})
    check("PATCH ride after trip → 409 (guard)", late.status_code == 409, str(late.status_code))


def main() -> int:
    print(f"→ {BASE}\n")
    with httpx.Client(base_url=BASE, timeout=25) as client:
        health = client.get("/health")
        check("GET /health", health.status_code == 200, str(health.json().get("version")))
        check("GET /meta (public)", client.get("/meta").status_code == 200)
        check("GET /auth/me without token → 401", client.get("/auth/me").status_code == 401)
        check(
            "wrong password → 401",
            client.post("/auth/login", json={"email": "nobody@ssuet.edu.pk", "password": "nope"}).status_code == 401,
        )

        driver, rider = Member(client), Member(client)
        driver.register("Driver")
        rider.register("Rider")

        check("GET /auth/me", driver.get("/auth/me").status_code == 200)
        driver.login()
        refreshed = client.post("/auth/refresh", json={"refresh_token": driver.refresh_token})
        check("POST /auth/refresh", refreshed.status_code == 200 and "access_token" in refreshed.json())
        driver.headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
        driver.refresh_token = refreshed.json()["refresh_token"]

        profile = driver.patch("/users/me", json={"home_area": "Gulistan-e-Johar"})
        nested = (profile.json().get("student_profile") or {}).get("home_area")
        check("PATCH /users/me", profile.status_code == 200 and nested == "Gulistan-e-Johar", str(profile.status_code))

        departure = (datetime.now(timezone.utc) + timedelta(minutes=20)).astimezone(TZ_KARACHI).isoformat()
        publish_and_complete(driver, rider, departure)

        logged_out = client.post(
            "/auth/logout", headers=driver.headers, json={"refresh_token": driver.refresh_token}
        )
        check("POST /auth/logout", logged_out.status_code in (200, 204), str(logged_out.status_code))
        check(
            "old refresh token rejected",
            client.post("/auth/refresh", json={"refresh_token": driver.refresh_token}).status_code == 401,
        )

    print("\nRESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILURE(S): {', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
