"""Development seed data (§18, §27).

Creates realistic SSUET community data so the mobile app and admin dashboard can
be developed against a populated database.

    python -m scripts.seed            # insert (skips if data already present)
    python -m scripts.seed --reset    # wipe domain data, then re-seed

Every seeded account uses the password: Password123!
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AdminAction, Base, Conversation, DeviceToken, Message, Notification, PasswordResetToken,
    RefreshToken, Report, Review, Ride, RideRequest, StudentProfile, TeacherProfile, Trip,
    User, UserBlock, Vehicle, Verification,
)
from app.models.enums import (  # noqa: E402
    AccountStatus, AdminActionType, ContributionType, FuelPreference, NotificationType,
    ReportCategory, ReportStatus, RideDirection, RideRequestStatus, RideStatus, TripStatus,
    UserRole, VehicleStatus, VehicleType, VerificationStatus, VerificationType,
)

random.seed(2026)
DEV_PASSWORD = "Password123!"
HASH = hash_password(DEV_PASSWORD)

SSUET = (settings.SSUET_LATITUDE, settings.SSUET_LONGITUDE)

AREAS = {
    "Gulshan-e-Iqbal": (24.9200, 67.0900),
    "Gulistan-e-Johar": (24.9200, 67.1400),
    "North Nazimabad": (24.9400, 67.0400),
    "Federal B Area": (24.9300, 67.0700),
    "PECHS": (24.8700, 67.0600),
    "Clifton": (24.8100, 67.0300),
    "Saddar": (24.8600, 67.0100),
    "Scheme 33": (24.9500, 67.1000),
    "Malir": (24.8900, 67.2000),
    "Korangi": (24.8400, 67.1200),
}

DEPARTMENTS = [
    "Computer Science", "Software Engineering", "Electrical Engineering",
    "Electronic Engineering", "Civil Engineering", "Biomedical Engineering",
    "Business Administration",
]


def _dt(days: int, hour: int, minute: int = 0) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(hour=hour - 5, minute=minute, second=0, microsecond=0)  # PKT -> UTC


def wipe(db: Session) -> None:
    print("Wiping existing data ...")
    for model in (
        AdminAction, Notification, DeviceToken, Message, Conversation, Review, Report,
        Trip, RideRequest, Ride, Vehicle, Verification, PasswordResetToken, RefreshToken,
        UserBlock, StudentProfile, TeacherProfile, User,
    ):
        db.execute(delete(model))
    db.commit()


def create_users(db: Session) -> dict[str, User]:
    people = [
        # key,            name,                    role,                 dept,                    area,              verified
        ("ali", "Ali Raza", UserRole.STUDENT, "Computer Science", "Gulshan-e-Iqbal", VerificationStatus.VERIFIED),
        ("ahmed", "Ahmed Hassan", UserRole.STUDENT, "Software Engineering", "Gulistan-e-Johar", VerificationStatus.VERIFIED),
        ("fatima", "Fatima Noor", UserRole.STUDENT, "Electrical Engineering", "North Nazimabad", VerificationStatus.VERIFIED),
        ("bilal", "Bilal Siddiqui", UserRole.STUDENT, "Civil Engineering", "PECHS", VerificationStatus.PENDING),
        ("hira", "Hira Kamran", UserRole.STUDENT, "Biomedical Engineering", "Clifton", VerificationStatus.VERIFIED),
        ("usman", "Usman Tariq", UserRole.STUDENT, "Computer Science", "Malir", VerificationStatus.UNVERIFIED),
        ("sana", "Sana Iqbal", UserRole.STUDENT, "Business Administration", "Federal B Area", VerificationStatus.VERIFIED),
        ("zain", "Zain Abbas", UserRole.STUDENT, "Electronic Engineering", "Korangi", VerificationStatus.SUSPENDED if False else VerificationStatus.VERIFIED),
        ("dr.faheem", "Dr. Faheem Ahmed", UserRole.TEACHER, "Computer Science", "Gulshan-e-Iqbal", VerificationStatus.VERIFIED),
        ("eng.nadia", "Engr. Nadia Farooq", UserRole.TEACHER, "Software Engineering", "Scheme 33", VerificationStatus.VERIFIED),
    ]

    users: dict[str, User] = {}
    for idx, (key, name, role, dept, area, vstatus) in enumerate(people, start=1):
        local = key.replace(".", "").replace(" ", "")
        email = f"{local}@ssuet.edu.pk"
        user = User(
            email=email,
            password_hash=HASH,
            phone=f"+92300123{idx:04d}",
            full_name=name,
            role=role,
            department=dept,
            university_id=(f"SSUET-EMP-{1000 + idx}" if role is UserRole.TEACHER else f"SSUET-{2022 + idx % 3}-{100 + idx}"),
            is_university_email=True,
            verification_status=vstatus,
            account_status=AccountStatus.SUSPENDED if key == "usman" else AccountStatus.ACTIVE,
            suspension_reason="Pending investigation of a reported ride" if key == "usman" else None,
            verified_at=datetime.now(timezone.utc) if vstatus is VerificationStatus.VERIFIED else None,
            email_verified_at=datetime.now(timezone.utc),
            rating_average=0.0,
            rating_count=0,
        )
        db.add(user)
        db.flush()

        if role is UserRole.STUDENT:
            db.add(StudentProfile(
                user_id=user.id, student_id=user.university_id, department=dept,
                degree_programme="BS " + dept, semester=random.randint(3, 8),
                batch_year=2022 + idx % 3, home_area=area,
            ))
        else:
            db.add(TeacherProfile(
                user_id=user.id, employee_id=user.university_id, department=dept,
                designation="Assistant Professor" if idx % 2 else "Lecturer", home_area=area,
            ))
        users[key] = user

    db.flush()

    # verification audit rows
    for key, user in users.items():
        if user.verification_status in (VerificationStatus.VERIFIED, VerificationStatus.PENDING):
            db.add(Verification(
                user_id=user.id,
                verification_type=VerificationType.UNIVERSITY_EMAIL,
                status=user.verification_status,
                submitted_value=user.email,
                reviewed_at=user.verified_at,
            ))
    db.commit()
    print(f"Created {len(users)} users (password: {DEV_PASSWORD})")
    return users


def create_vehicles(db: Session, users: dict[str, User]) -> dict[str, Vehicle]:
    specs = [
        ("ali", VehicleType.CAR, "Toyota Corolla 2019", "White", "ABC-1234", 4, VehicleStatus.VERIFIED),
        ("dr.faheem", VehicleType.CAR, "Honda Civic 2021", "Black", "KHI-8890", 4, VehicleStatus.VERIFIED),
        ("fatima", VehicleType.CAR, "Suzuki Alto 2017", "Silver", "BXK-4412", 3, VehicleStatus.VERIFIED),
        ("bilal", VehicleType.BIKE, "Honda CD 70", "Red", "KHI-7712", 1, VehicleStatus.PENDING),
        ("eng.nadia", VehicleType.CAR, "Toyota Yaris 2020", "Blue", "QRS-3321", 4, VehicleStatus.VERIFIED),
        ("hira", VehicleType.BIKE, "Yamaha YBR 125", "Black", "MDL-9081", 1, VehicleStatus.PENDING),
    ]
    vehicles: dict[str, Vehicle] = {}
    for key, vtype, model, color, reg, capacity, status in specs:
        v = Vehicle(
            owner_id=users[key].id, vehicle_type=vtype, make_and_model=model, color=color,
            registration_number=reg, passenger_capacity=capacity, is_primary=True, status=status,
            reviewed_at=datetime.now(timezone.utc) if status is VehicleStatus.VERIFIED else None,
        )
        db.add(v)
        vehicles[key] = v
    db.commit()
    print(f"Created {len(vehicles)} vehicles")
    return vehicles


def create_rides(db: Session, users: dict[str, User], vehicles: dict[str, Vehicle]) -> list[Ride]:
    """Open rides for Explore (§8) across several days and both directions."""
    plans = [
        ("ali", "Gulshan-e-Iqbal", RideDirection.HOME_TO_UNIVERSITY, 1, 8, 0, FuelPreference.SHARE_FUEL, ContributionType.FIXED, 150),
        ("dr.faheem", "Gulshan-e-Iqbal", RideDirection.HOME_TO_UNIVERSITY, 1, 7, 45, FuelPreference.FREE, ContributionType.NONE, None),
        ("fatima", "North Nazimabad", RideDirection.HOME_TO_UNIVERSITY, 1, 8, 15, FuelPreference.SHARE_FUEL, ContributionType.NEGOTIABLE, None),
        ("eng.nadia", "Scheme 33", RideDirection.UNIVERSITY_TO_HOME, 1, 17, 0, FuelPreference.FREE, ContributionType.NONE, None),
        ("ali", "Gulshan-e-Iqbal", RideDirection.UNIVERSITY_TO_HOME, 1, 17, 30, FuelPreference.SHARE_FUEL, ContributionType.EXPECTED, 100),
        ("bilal", "PECHS", RideDirection.HOME_TO_UNIVERSITY, 2, 8, 30, FuelPreference.FREE, ContributionType.NONE, None),
        ("fatima", "North Nazimabad", RideDirection.UNIVERSITY_TO_HOME, 2, 16, 45, FuelPreference.SHARE_FUEL, ContributionType.FIXED, 120),
        ("dr.faheem", "Gulshan-e-Iqbal", RideDirection.HOME_TO_UNIVERSITY, 3, 7, 30, FuelPreference.FREE, ContributionType.NONE, None),
    ]
    notes = [
        "Leaving sharp at 8:00, please be on time.",
        "AC car, no smoking inside please.",
        "Can pick up from the main signal near the bus stop.",
        None,
        "Returning right after the last lecture.",
        None,
        "Prefer someone from the same department.",
        "Morning ride, quiet music only.",
    ]
    rides: list[Ride] = []
    for i, (key, area, direction, day, hour, minute, fuel, ctype, amount) in enumerate(plans):
        driver = users[key]
        veh = vehicles.get(key)
        lat, lng = AREAS[area]
        to_uni = direction is RideDirection.HOME_TO_UNIVERSITY
        departure = _dt(day, hour, minute)
        ride = Ride(
            driver_id=driver.id,
            vehicle_id=veh.id if veh else None,
            vehicle_type=veh.vehicle_type if veh else VehicleType.CAR,
            direction=direction,
            pickup_area=area if to_uni else "SSUET, University Road",
            pickup_latitude=lat if to_uni else SSUET[0],
            pickup_longitude=lng if to_uni else SSUET[1],
            destination_area="SSUET, University Road" if to_uni else area,
            destination_latitude=SSUET[0] if to_uni else lat,
            destination_longitude=SSUET[1] if to_uni else lng,
            departure_date=departure,
            departure_at=departure,
            available_seats=1,
            seats_remaining=1,
            fuel_preference=fuel,
            contribution_type=ctype,
            contribution_amount=amount,
            contribution_note=(
                "Fuel share, cash on the way." if fuel is FuelPreference.SHARE_FUEL else None
            ),
            note=notes[i],
            status=RideStatus.OPEN,
        )
        db.add(ride)
        rides.append(ride)
    db.commit()
    print(f"Created {len(rides)} open rides")
    return rides


def create_matched_trip(db: Session, users: dict[str, User], rides: list[Ride]) -> Trip:
    """One MATCHED ride with an accepted request, trip, chat and reviews."""
    ride = rides[2]  # Fatima's ride
    passenger = users["sana"]
    now = datetime.now(timezone.utc)

    request = RideRequest(
        ride_id=ride.id, passenger_id=passenger.id, status=RideRequestStatus.ACCEPTED,
        message="Assalam o Alaikum, I live near Five Star Chowrangi. Can I join?",
        responded_at=now,
    )
    db.add(request)
    db.flush()

    ride.status = RideStatus.MATCHED
    ride.seats_remaining = 0
    ride.matched_at = now

    trip = Trip(
        ride_id=ride.id, request_id=request.id, driver_id=ride.driver_id,
        passenger_id=passenger.id, status=TripStatus.CONFIRMED,
        meeting_point="Five Star Chowrangi, opposite Shell pump",
        meeting_latitude=24.9280, meeting_longitude=67.0460,
    )
    db.add(trip)
    db.flush()

    convo = Conversation(trip_id=trip.id, last_message_at=now, last_message_preview="See you at 8:15!")
    db.add(convo)
    db.flush()
    db.add_all([
        Message(conversation_id=convo.id, sender_id=ride.driver_id, body="Salam! Request accepted.", read_at=now),
        Message(conversation_id=convo.id, sender_id=passenger.id, body="Thank you so much! Where exactly should I wait?", read_at=now),
        Message(conversation_id=convo.id, sender_id=ride.driver_id, body="Five Star Chowrangi, opposite Shell pump. See you at 8:15!"),
    ])

    # completed trip in the past → produces ratings and completed counts
    past_ride = Ride(
        driver_id=users["dr.faheem"].id,
        vehicle_id=None,
        vehicle_type=VehicleType.CAR,
        direction=RideDirection.HOME_TO_UNIVERSITY,
        pickup_area="Gulshan-e-Iqbal", pickup_latitude=24.92, pickup_longitude=67.09,
        destination_area="SSUET, University Road",
        destination_latitude=SSUET[0], destination_longitude=SSUET[1],
        departure_date=_dt(-4, 8), departure_at=_dt(-4, 8),
        available_seats=1, seats_remaining=0,
        fuel_preference=FuelPreference.FREE, contribution_type=ContributionType.NONE,
        status=RideStatus.COMPLETED, matched_at=_dt(-5, 12), started_at=_dt(-4, 8),
        completed_at=_dt(-4, 9),
    )
    db.add(past_ride)
    db.flush()
    past_request = RideRequest(
        ride_id=past_ride.id, passenger_id=users["ahmed"].id,
        status=RideRequestStatus.ACCEPTED, responded_at=_dt(-5, 12),
    )
    db.add(past_request)
    db.flush()
    past_trip = Trip(
        ride_id=past_ride.id, request_id=past_request.id,
        driver_id=past_ride.driver_id, passenger_id=past_request.passenger_id,
        status=TripStatus.COMPLETED, started_at=_dt(-4, 8), completed_at=_dt(-4, 9),
        driver_confirmed_complete=True, passenger_confirmed_complete=True,
        driver_reviewed_passenger=True, passenger_reviewed_driver=True,
    )
    db.add(past_trip)
    db.flush()
    db.add_all([
        Review(trip_id=past_trip.id, author_id=past_ride.driver_id, subject_id=past_request.passenger_id,
               rating=5, comment="Polite and on time."),
        Review(trip_id=past_trip.id, author_id=past_request.passenger_id, subject_id=past_ride.driver_id,
               rating=5, comment="Very punctual and friendly teacher."),
    ])
    for u, total in ((users["dr.faheem"], 5), (users["ahmed"], 5)):
        u.rating_average, u.rating_count, u.completed_trips_count = float(total), 1, 1

    # a pending request on Ali's ride (driver-side notification demo)
    db.add(RideRequest(
        ride_id=rides[0].id, passenger_id=users["hira"].id, status=RideRequestStatus.PENDING,
        message="Heading to campus for the 9 AM lab, can I join?",
    ))
    db.add(Notification(
        user_id=rides[0].driver_id, type=NotificationType.RIDE_REQUEST_RECEIVED,
        title="New ride request", body="Hira Kamran wants to join your Gulshan-e-Iqbal ride.",
        data={"screen": "my-rides", "tab": "published"},
    ))

    # one open complaint for the admin dashboard
    db.add(Report(
        reporter_id=users["ahmed"].id, reported_user_id=users["usman"].id, ride_id=rides[5].id,
        category=ReportCategory.MISLEADING_RIDE,
        description="The ride said free but the driver asked for cash at the end of the journey.",
        status=ReportStatus.OPEN,
    ))
    db.add(AdminAction(
        admin_id=None, action_type=AdminActionType.SUSPEND_USER, target_user_id=users["usman"].id,
        notes="Account suspended pending investigation of report.",
    ))
    db.commit()
    print("Created 1 matched trip (with chat), 1 completed trip (with reviews), 1 report")
    return trip


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SSUET RideShare development data")
    parser.add_argument("--reset", action="store_true", help="delete existing domain data first")
    args = parser.parse_args()

    if settings.is_production:
        raise SystemExit("Refusing to seed a production database.")

    Base.metadata.create_all(bind=engine)  # no-op if Alembic already migrated
    with SessionLocal() as db:
        if args.reset:
            wipe(db)
        elif db.scalar(select(User.id).limit(1)) is not None:
            print("Database already contains data. Use --reset to re-seed.")
            return

        users = create_users(db)
        vehicles = create_vehicles(db, users)
        rides = create_rides(db, users, vehicles)
        create_matched_trip(db, users, rides)

    print("\nSeed complete.")
    print("Login example: ali@ssuet.edu.pk / Password123!")


if __name__ == "__main__":
    main()
