"""Load sanity check for the read paths students hit most (§23).

This is deliberately a *sanity* check, not a benchmark suite: it answers "does
Explore stay responsive with a few hundred live journeys and a burst of
concurrent members?" using the same HTTP API the app uses.

Usage
-----
```bash
# 1. point at a throwaway database and start the API
export DATABASE_URL="sqlite+pysqlite:///./load_test.db"
export AUTO_CREATE_TABLES=true

# 2. create the dataset (400 rides, 40 drivers, one passenger account)
python -m scripts.load_check seed --drivers 40 --rides-per-driver 10

# 3. run the API, then measure it
python -m uvicorn app.main:app --port 8010 &
python -m scripts.load_check run --base-url http://127.0.0.1:8010/api/v1 \
    --requests 400 --concurrency 20
```

The report prints p50/p95/p99 latency and the error count per endpoint.

Two ways to point it at a running system:

* **the way it should be measured** — at the real stack (PostgreSQL + gunicorn +
  nginx + TLS), which is what doc 18 §3 records:
      python -m scripts.load_check run \
          --base-url https://rideshare.ssuet.edu.pk/api/v1 --insecure \
          --requests 200 --concurrency 20
* straight at `uvicorn` during development, which measures the app but not the proxy.

SQLite is single-writer: the numbers worth quoting come from PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

PASSWORD = "LoadTest123"
START_AREAS = [
    "Gulshan-e-Iqbal",
    "North Nazimabad",
    "Gulistan-e-Johar",
    "Saddar",
    "Malir",
    "Korangi",
    "Federal B Area",
    "Clifton",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- seeding
def seed(drivers: int, rides_per_driver: int) -> None:
    """Insert a realistic pile of journeys straight through the ORM."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.security import hash_password
    from app.db.session import SessionLocal, engine
    from app.models import Base
    from app.models.enums import (
        AccountStatus,
        ContributionType,
        FuelPreference,
        RideDirection,
        RideStatus,
        UserRole,
        VehicleStatus,
        VehicleType,
        VerificationStatus,
    )
    from app.models.ride import Ride
    from app.models.user import User
    from app.models.vehicle import Vehicle

    # Standalone process: the API's lifespan hook is not running, so create the
    # schema ourselves when the throwaway-database flag is on.
    if settings.AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == "load-driver-0@ssuet.edu.pk"))
        if existing is not None:
            print("Dataset already present — nothing to seed.")
            return

        created = 0
        for index in range(drivers):
            driver = User(
                email=f"load-driver-{index}@ssuet.edu.pk",
                password_hash=hash_password(PASSWORD),
                phone=f"+9233{uuid.uuid4().int % 10**8:08d}",
                full_name=f"Load Driver {index}",
                role=UserRole.STUDENT,
                department="Computer Science",
                university_id=f"LOAD-{index:04d}",
                is_university_email=True,
                verification_status=VerificationStatus.VERIFIED,
                account_status=AccountStatus.ACTIVE,
            )
            db.add(driver)
            db.flush()

            vehicle = Vehicle(
                owner_id=driver.id,
                vehicle_type=VehicleType.CAR,
                make_and_model="Suzuki Alto 2020",
                color="White",
                registration_number=f"LOD-{index:04d}",
                passenger_capacity=1,
                status=VehicleStatus.VERIFIED,
            )
            db.add(vehicle)
            db.flush()

            for slot in range(rides_per_driver):
                departure = _utcnow() + timedelta(hours=1 + slot * 2)
                fuel_preference = random.choice(list(FuelPreference))
                db.add(
                    Ride(
                        driver_id=driver.id,
                        vehicle_id=vehicle.id,
                        vehicle_type=VehicleType.CAR,
                        direction=RideDirection.HOME_TO_UNIVERSITY,
                        pickup_area=random.choice(START_AREAS),
                        pickup_latitude=24.90 + random.random() * 0.12,
                        pickup_longitude=67.03 + random.random() * 0.12,
                        destination_area="SSUET, University Road, Karachi",
                        destination_latitude=24.9460,
                        destination_longitude=67.1157,
                        departure_date=departure.replace(hour=0, minute=0, second=0, microsecond=0),
                        departure_at=departure,
                        available_seats=1,
                        seats_remaining=1,
                        fuel_preference=fuel_preference,
                        contribution_type=(
                            ContributionType.NEGOTIABLE
                            if fuel_preference is FuelPreference.SHARE_FUEL
                            else ContributionType.NONE
                        ),
                        note="Load-test journey.",
                        status=RideStatus.OPEN,
                    )
                )
                created += 1

        # one passenger used by the load generator
        passenger = User(
            email="load-passenger@ssuet.edu.pk",
            password_hash=hash_password(PASSWORD),
            phone="+923000000000",
            full_name="Load Passenger",
            role=UserRole.STUDENT,
            department="Software Engineering",
            university_id="LOAD-PAX",
            is_university_email=True,
            verification_status=VerificationStatus.VERIFIED,
            account_status=AccountStatus.ACTIVE,
        )
        db.add(passenger)
        db.commit()
        print(f"Seeded {drivers} drivers, {created} rides and 1 passenger account.")
    finally:
        db.close()


# ------------------------------------------------------------------- measuring
def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def run(base_url: str, requests: int, concurrency: int, verify: bool = True) -> dict:
    login = httpx.post(
        f"{base_url}/auth/login",
        json={"email": "load-passenger@ssuet.edu.pk", "password": PASSWORD},
        timeout=30,
        verify=verify,
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client = httpx.Client(
        base_url=base_url, headers=headers, timeout=30, follow_redirects=True, verify=verify
    )

    feed = client.get("/rides", params={"limit": 20}).json()
    ride_ids = [item["id"] for item in feed.get("items", [])][:50]
    if not ride_ids:
        print("No rides to read — seed the dataset first.")
        return {}

    endpoints: dict[str, tuple[str, dict]] = {
        "explore (default)": ("/rides", {"limit": 20}),
        "explore (filtered)": (
            "/rides",
            {"direction": "HOME_TO_UNIVERSITY", "pickup_area": "Gulshan-e-Iqbal", "limit": 20},
        ),
        "explore (nearby)": (
            "/rides",
            {"latitude": 24.92, "longitude": 67.09, "radius_km": 8, "limit": 20},
        ),
        "ride detail": (f"/rides/{ride_ids[0]}", {}),
        "my trips": ("/trips/mine", {}),
        "notifications": ("/notifications", {"limit": 20}),
        "explore (small page)": ("/rides", {"limit": 5}),
    }

    report: dict[str, dict] = {}
    for label, (path, params) in endpoints.items():
        latencies: list[float] = []
        errors = 0

        def one(_: int) -> None:
            nonlocal errors
            started = time.perf_counter()
            try:
                response = client.get(path, params=params)
                if response.status_code >= 400:
                    errors += 1
            except httpx.HTTPError:
                errors += 1
            finally:
                latencies.append((time.perf_counter() - started) * 1000)

        started_at = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(one, range(requests)))
        elapsed = max(time.perf_counter() - started_at, 1e-6)

        report[label] = {
            "requests": requests,
            "errors": errors,
            "rps": round(requests / elapsed, 1),
            "p50_ms": round(_percentile(latencies, 0.50), 1),
            "p95_ms": round(_percentile(latencies, 0.95), 1),
            "p99_ms": round(_percentile(latencies, 0.99), 1),
            "mean_ms": round(statistics.fmean(latencies), 1),
            "max_ms": round(max(latencies), 1),
        }

    client.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="SSUET RideShare load sanity check")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_cmd = sub.add_parser("seed", help="create a synthetic dataset in the configured database")
    seed_cmd.add_argument("--drivers", type=int, default=40)
    seed_cmd.add_argument("--rides-per-driver", type=int, default=10)

    run_cmd = sub.add_parser("run", help="measure the read endpoints")
    run_cmd.add_argument("--base-url", default="http://127.0.0.1:8010/api/v1")
    run_cmd.add_argument("--requests", type=int, default=300)
    run_cmd.add_argument("--concurrency", type=int, default=20)
    run_cmd.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (self-signed certificate during a rehearsal)",
    )

    args = parser.parse_args()
    if args.command == "seed":
        seed(args.drivers, args.rides_per_driver)
        return 0

    report = run(args.base_url, args.requests, args.concurrency, verify=not args.insecure)
    if not report:
        return 1
    print(f"\nLoad sanity — {args.requests} requests/endpoint, concurrency {args.concurrency}\n")
    print(f"{'endpoint':26} {'rps':>7} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'errors':>7}")
    for label, row in report.items():
        print(
            f"{label:26} {row['rps']:7.1f} {row['p50_ms']:8.1f} {row['p95_ms']:8.1f} "
            f"{row['p99_ms']:8.1f} {row['max_ms']:8.1f} {row['errors']:7d}"
        )
    print("\nJSON:", json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
