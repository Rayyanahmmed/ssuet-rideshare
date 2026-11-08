"""Database-level guarantees (§9, §14, §18).

These tests exercise the *database* rules, not application code — the backend
must never be the only line of defence for the one-passenger business rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Conversation,
    Message,
    Review,
    Ride,
    RideRequest,
    Trip,
    User,
    Vehicle,
)
from app.models.enums import (
    ContributionType,
    FuelPreference,
    RideDirection,
    RideRequestStatus,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleType,
)
from tests.conftest import make_user

NOW = datetime.now(timezone.utc)


def make_ride(db, driver: User, **overrides) -> Ride:
    data = dict(
        driver_id=driver.id,
        vehicle_type=VehicleType.CAR,
        direction=RideDirection.HOME_TO_UNIVERSITY,
        pickup_area="Gulshan-e-Iqbal",
        pickup_latitude=24.92,
        pickup_longitude=67.09,
        destination_area="SSUET, University Road",
        destination_latitude=24.9372,
        destination_longitude=67.1138,
        departure_date=NOW + timedelta(hours=5),
        departure_at=NOW + timedelta(hours=5),
        available_seats=1,
        seats_remaining=1,
        fuel_preference=FuelPreference.FREE,
        contribution_type=ContributionType.NONE,
    )
    data.update(overrides)
    ride = Ride(**data)
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


def accept(db, ride: Ride, passenger: User) -> Trip:
    request = RideRequest(ride_id=ride.id, passenger_id=passenger.id, status=RideRequestStatus.ACCEPTED)
    db.add(request)
    db.commit()
    trip = Trip(ride_id=ride.id, request_id=request.id, driver_id=ride.driver_id, passenger_id=passenger.id)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def test_ride_requires_valid_seat_count(db):
    driver = make_user(db)
    with pytest.raises(IntegrityError):
        make_ride(db, driver, available_seats=0)
    db.rollback()


def test_fuel_share_requires_contribution_type(db):
    driver = make_user(db)
    with pytest.raises(IntegrityError):
        make_ride(
            db, driver,
            fuel_preference=FuelPreference.SHARE_FUEL,
            contribution_type=ContributionType.NONE,  # SHARE_FUEL needs FIXED/EXPECTED/NEGOTIABLE
        )
    db.rollback()


def test_second_live_trip_on_same_ride_is_impossible(db):
    driver = make_user(db, role=UserRole.TEACHER)
    p1, p2 = make_user(db), make_user(db)
    ride = make_ride(db, driver)

    accept(db, ride, p1)
    with pytest.raises(IntegrityError):
        accept(db, ride, p2)
    db.rollback()


def test_cancelled_trip_frees_the_ride_for_a_new_passenger(db):
    driver = make_user(db)
    p1, p2 = make_user(db), make_user(db)
    ride = make_ride(db, driver)

    trip = accept(db, ride, p1)
    trip.status = TripStatus.CANCELLED
    db.commit()

    second = accept(db, ride, p2)
    assert second.id != trip.id


def test_only_one_pending_request_per_passenger_and_ride(db):
    driver = make_user(db)
    passenger = make_user(db)
    ride = make_ride(db, driver)

    db.add(RideRequest(ride_id=ride.id, passenger_id=passenger.id, status=RideRequestStatus.PENDING))
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(RideRequest(ride_id=ride.id, passenger_id=passenger.id, status=RideRequestStatus.PENDING))
        db.commit()
    db.rollback()


def test_driver_cannot_join_own_ride(db):
    driver = make_user(db)
    ride = make_ride(db, driver)
    with pytest.raises(IntegrityError):
        accept(db, ride, driver)
    db.rollback()


def test_review_is_unique_per_trip_and_author(db):
    driver = make_user(db)
    passenger = make_user(db)
    ride = make_ride(db, driver)
    trip = accept(db, ride, passenger)

    db.add(Review(trip_id=trip.id, author_id=passenger.id, subject_id=driver.id, rating=5))
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(Review(trip_id=trip.id, author_id=passenger.id, subject_id=driver.id, rating=4))
        db.commit()
    db.rollback()


def test_review_rating_range_is_enforced(db):
    driver = make_user(db)
    passenger = make_user(db)
    ride = make_ride(db, driver)
    trip = accept(db, ride, passenger)
    with pytest.raises(IntegrityError):
        db.add(Review(trip_id=trip.id, author_id=passenger.id, subject_id=driver.id, rating=6))
        db.commit()
    db.rollback()


def test_user_email_and_phone_are_unique(db):
    user = make_user(db)
    with pytest.raises(IntegrityError):
        db.add(
            User(
                email=user.email,
                password_hash=user.password_hash,
                phone="+923001119999",
                full_name="Duplicate Email",
                role=UserRole.STUDENT,
                department="CS",
                university_id="SSUET-DUP-1",
            )
        )
        db.commit()
    db.rollback()


def test_foreign_keys_are_enforced_in_sqlite(db):
    with pytest.raises(IntegrityError):
        db.add(
            Vehicle(
                owner_id=uuid.uuid4(),  # non-existent user
                vehicle_type=VehicleType.CAR,
                make_and_model="Corolla",
                color="White",
                registration_number="ZZZ-000",
                passenger_capacity=1,
            )
        )
        db.commit()
    db.rollback()


def test_conversation_is_one_per_trip(db):
    driver = make_user(db)
    passenger = make_user(db)
    ride = make_ride(db, driver)
    trip = accept(db, ride, passenger)

    db.add(Conversation(trip_id=trip.id))
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(Conversation(trip_id=trip.id))
        db.commit()
    db.rollback()


def test_messages_belong_to_a_conversation(db):
    driver = make_user(db)
    passenger = make_user(db)
    ride = make_ride(db, driver)
    trip = accept(db, ride, passenger)
    convo = Conversation(trip_id=trip.id)
    db.add(convo)
    db.commit()

    db.add(Message(conversation_id=convo.id, sender_id=passenger.id, body="Salam!"))
    db.commit()
    stored = db.scalars(select(Message).where(Message.conversation_id == convo.id)).all()
    assert len(stored) == 1
    assert stored[0].read_at is None  # unread indicator starts empty


def test_soft_delete_keeps_the_row(db):
    user = make_user(db)
    user.deleted_at = NOW
    db.commit()
    assert db.scalar(select(User).where(User.id == user.id)) is not None
    assert user.is_deleted
