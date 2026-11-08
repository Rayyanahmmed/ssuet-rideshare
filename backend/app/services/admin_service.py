"""Admin operations (§16, §17).

Two rules shape this module:

1. **Every mutation writes an `admin_actions` row.** Verification decisions,
   suspensions, vehicle approvals, ride cancellations and report handling are all
   recorded with the acting admin, the target and the reason. The log is the
   audit trail; nothing is deleted from it.
2. **The affected member is told.** Each decision sends the existing notification
   templates, so an approval or a suspension reaches the person in the app and as
   a push — the admin console never silently changes someone's account.

Read endpoints are page-numbered and every aggregate is computed from the live
tables: there is no hardcoded statistics anywhere in the dashboard.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.admin_action import AdminAction
from app.models.enums import (
    ReportCategory,
    AccountStatus,
    AdminActionType,
    NotificationType,
    ReportStatus,
    RideRequestStatus,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
    VerificationStatus,
    VerificationType,
)
from app.models.report import Report
from app.models.review import Review
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.verification import Verification
from app.schemas.admin import (
    AdminActionRow,
    AdminReportRow,
    AdminReviewRow,
    AdminRideRow,
    AdminTripRow,
    AdminUserDetail,
    AdminUserRow,
    AdminVehicleRow,
    AdminVerificationRow,
    AnalyticsOut,
    DashboardOut,
    DashboardStats,
    SettingsOut,
    TrendPoint,
)
from app.services import ride_service, review_service
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.admin")

TREND_DAYS = 14


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------- helpers
def _count(db: Session, query: Select) -> int:
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def _paginate(db: Session, query: Select, page: int, limit: int) -> tuple[list[Any], int, int]:
    page = max(1, page)
    limit = max(1, min(limit, 100))
    total = _count(db, query)
    rows = list(db.scalars(query.limit(limit).offset((page - 1) * limit)).all())
    pages = max(1, -(-total // limit))
    return rows, total, pages


def record_action(
    db: Session,
    *,
    admin: User,
    action_type: AdminActionType,
    target_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> None:
    """Public wrapper for settings/integration changes that touch no single member."""
    _log_action(
        db,
        admin=admin,
        action_type=action_type,
        target_user_id=target_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        notes=notes,
    )
    db.commit()


def _log_action(
    db: Session,
    *,
    admin: User,
    action_type: AdminActionType,
    target_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> None:
    db.add(
        AdminAction(
            admin_id=admin.id,
            action_type=action_type,
            target_user_id=target_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            report_id=report_id,
            notes=notes,
        )
    )


def _trend(db: Session, column, days: int = TREND_DAYS) -> list[TrendPoint]:
    """Daily counts for the last `days` days, zero-filled so charts never lie."""
    start = (utcnow() - timedelta(days=days - 1)).date()
    rows = db.execute(
        select(func.date(column), func.count()).where(column >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)).group_by(func.date(column))
    ).all()
    counts = {str(day): int(count) for day, count in rows}
    return [
        TrendPoint(day=start + timedelta(days=offset), count=counts.get(str(start + timedelta(days=offset)), 0))
        for offset in range(days)
    ]


def _status_counts(db: Session, model, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).select_from(model).group_by(column)).all()
    return {str(status): int(count) for status, count in rows}


# ------------------------------------------------------------------- dashboard
def dashboard(db: Session) -> DashboardOut:
    today_start = datetime.combine(utcnow().date(), datetime.min.time(), tzinfo=timezone.utc)

    stats = DashboardStats(
        total_users=int(db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0),
        verified_users=int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.verification_status == VerificationStatus.VERIFIED)
            )
            or 0
        ),
        pending_verifications=int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.verification_status == VerificationStatus.PENDING)
            )
            or 0
        ),
        pending_vehicles=int(
            db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.status == VehicleStatus.PENDING))
            or 0
        ),
        suspended_accounts=int(
            db.scalar(
                select(func.count()).select_from(User).where(User.account_status == AccountStatus.SUSPENDED)
            )
            or 0
        ),
        published_rides=int(db.scalar(select(func.count()).select_from(Ride)) or 0),
        open_rides=int(
            db.scalar(select(func.count()).select_from(Ride).where(Ride.status == RideStatus.OPEN)) or 0
        ),
        active_trips=int(
            db.scalar(
                select(func.count())
                .select_from(Trip)
                .where(Trip.status.in_([TripStatus.CONFIRMED, TripStatus.IN_PROGRESS]))
            )
            or 0
        ),
        completed_trips=int(
            db.scalar(select(func.count()).select_from(Trip).where(Trip.status == TripStatus.COMPLETED)) or 0
        ),
        open_reports=int(
            db.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.status.in_([ReportStatus.OPEN, ReportStatus.UNDER_REVIEW]))
            )
            or 0
        ),
        rides_today=int(
            db.scalar(select(func.count()).select_from(Ride).where(Ride.created_at >= today_start)) or 0
        ),
        trips_today=int(
            db.scalar(select(func.count()).select_from(Trip).where(Trip.created_at >= today_start)) or 0
        ),
    )

    return DashboardOut(
        stats=stats,
        users_per_day=_trend(db, User.created_at),
        rides_per_day=_trend(db, Ride.created_at),
        trips_per_day=_trend(db, Trip.created_at),
        rides_by_status=_status_counts(db, Ride, Ride.status),
        trips_by_status=_status_counts(db, Trip, Trip.status),
        generated_at=utcnow(),
    )


def analytics(db: Session, days: int = 30) -> AnalyticsOut:
    total_trips = int(db.scalar(select(func.count()).select_from(Trip)) or 0)
    completed = int(
        db.scalar(select(func.count()).select_from(Trip).where(Trip.status == TripStatus.COMPLETED)) or 0
    )
    cancelled = int(
        db.scalar(select(func.count()).select_from(Trip).where(Trip.status == TripStatus.CANCELLED)) or 0
    )
    average_rating = float(
        db.scalar(
            select(func.avg(User.rating_average)).where(User.rating_count > 0)
        )
        or 0.0
    )

    fuel_split = _status_counts(db, Ride, Ride.fuel_preference)
    vehicle_split = _status_counts(db, Ride, Ride.vehicle_type)
    direction_split = _status_counts(db, Ride, Ride.direction)

    top_pickup = [
        {"area": area, "count": int(count)}
        for area, count in db.execute(
            select(Ride.pickup_area, func.count()).group_by(Ride.pickup_area).order_by(func.count().desc()).limit(6)
        ).all()
    ]
    top_destination = [
        {"area": area, "count": int(count)}
        for area, count in db.execute(
            select(Ride.destination_area, func.count())
            .group_by(Ride.destination_area)
            .order_by(func.count().desc())
            .limit(6)
        ).all()
    ]

    return AnalyticsOut(
        days=days,
        completion_rate=round(completed / total_trips * 100, 1) if total_trips else 0.0,
        cancellation_rate=round(cancelled / total_trips * 100, 1) if total_trips else 0.0,
        average_rating=round(average_rating, 2),
        fuel_split=fuel_split,
        vehicle_split=vehicle_split,
        direction_split=direction_split,
        top_pickup_areas=top_pickup,
        top_destinations=top_destination,
        users_per_day=_trend(db, User.created_at, days),
        rides_per_day=_trend(db, Ride.created_at, days),
    )


# ----------------------------------------------------------------------- users
def _user_row(user: User, vehicles_count: int = 0) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        department=user.department,
        university_id=user.university_id,
        verification_status=user.verification_status,
        account_status=user.account_status,
        rating_average=user.rating_average,
        rating_count=user.rating_count,
        completed_trips_count=user.completed_trips_count,
        vehicles_count=vehicles_count,
        profile_photo_url=user.photo_url,
        created_at=_aware(user.created_at),
        last_login_at=_aware(user.last_login_at),
    )


def user_row(db: Session, user: User) -> AdminUserRow:
    """Single-row serialiser (used by the mutation endpoints)."""
    vehicles_count = int(
        db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.owner_id == user.id)) or 0
    )
    return _user_row(user, vehicles_count)


def list_users(
    db: Session,
    *,
    search: str | None = None,
    role: UserRole | None = None,
    status: AccountStatus | None = None,
    verification: VerificationStatus | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminUserRow], int, int]:
    query = select(User).where(User.deleted_at.is_(None))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.university_id.ilike(like),
                User.phone.ilike(like),
            )
        )
    if role is not None:
        query = query.where(User.role == role)
    if status is not None:
        query = query.where(User.account_status == status)
    if verification is not None:
        query = query.where(User.verification_status == verification)

    query = query.order_by(User.created_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    vehicle_counts = dict(
        db.execute(
            select(Vehicle.owner_id, func.count())
            .where(Vehicle.owner_id.in_([row.id for row in rows] or [uuid.uuid4()]))
            .group_by(Vehicle.owner_id)
        ).all()
    )
    return [_user_row(row, int(vehicle_counts.get(row.id, 0))) for row in rows], total, pages


def get_user_detail(db: Session, user_id: uuid.UUID) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("This member could not be found.")

    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.owner_id == user.id)).all())
    rides = list(
        db.scalars(
            select(Ride)
            .where(Ride.driver_id == user.id)
            .order_by(Ride.created_at.desc())
            .limit(10)
            .options(selectinload(Ride.requests))
        ).all()
    )
    verifications = list(
        db.scalars(
            select(Verification)
            .where(Verification.user_id == user.id)
            .order_by(Verification.created_at.desc())
        ).all()
    )

    return AdminUserDetail(
        user=_user_row(user, len(vehicles)),
        email_verified_at=_aware(user.email_verified_at),
        verified_at=_aware(user.verified_at),
        suspension_reason=user.suspension_reason,
        home_area=(
            user.student_profile.home_area
            if user.student_profile is not None
            else (user.teacher_profile.home_area if user.teacher_profile is not None else None)
        ),
        semester=user.student_profile.semester if user.student_profile is not None else None,
        vehicles=[_vehicle_row(vehicle) for vehicle in vehicles],
        recent_rides=[_ride_row(ride) for ride in rides],
        verifications=[_verification_row(row) for row in verifications],
        trips_as_driver=int(
            db.scalar(select(func.count()).select_from(Trip).where(Trip.driver_id == user.id)) or 0
        ),
        trips_as_passenger=int(
            db.scalar(select(func.count()).select_from(Trip).where(Trip.passenger_id == user.id)) or 0
        ),
        reports_against=int(
            db.scalar(select(func.count()).select_from(Report).where(Report.reported_user_id == user.id)) or 0
        ),
        reports_filed=int(
            db.scalar(select(func.count()).select_from(Report).where(Report.reporter_id == user.id)) or 0
        ),
    )


def _target_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("This member could not be found.")
    if user.role is UserRole.ADMIN:
        raise ConflictError("Administrator accounts cannot be modified from this console.")
    return user


def verify_user(db: Session, admin: User, user_id: uuid.UUID, note: str | None = None) -> User:
    user = _target_user(db, user_id)
    if user.verification_status is VerificationStatus.VERIFIED:
        raise ConflictError("This member is already verified.")

    user.verification_status = VerificationStatus.VERIFIED
    user.verified_at = utcnow()
    for verification in db.scalars(
        select(Verification).where(
            Verification.user_id == user.id, Verification.status == VerificationStatus.PENDING
        )
    ):
        verification.status = VerificationStatus.VERIFIED
        verification.reviewed_by_id = admin.id
        verification.reviewed_at = utcnow()
        verification.review_note = note

    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.VERIFY_USER,
        target_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        notes=note,
    )
    create_notification_from_template(
        db, user_id=user.id, template="ACCOUNT_VERIFIED", commit=False, name_suffix=""
    )
    db.commit()
    db.refresh(user)
    return user


def reject_user(
    db: Session, admin: User, user_id: uuid.UUID, reason: str | None = None
) -> User:
    user = _target_user(db, user_id)
    if user.verification_status is VerificationStatus.REJECTED:
        raise ConflictError("This member's verification is already rejected.")

    user.verification_status = VerificationStatus.REJECTED
    for verification in db.scalars(
        select(Verification).where(
            Verification.user_id == user.id, Verification.status == VerificationStatus.PENDING
        )
    ):
        verification.status = VerificationStatus.REJECTED
        verification.reviewed_by_id = admin.id
        verification.reviewed_at = utcnow()
        verification.review_note = reason

    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.REJECT_USER_VERIFICATION,
        target_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        notes=reason,
    )
    db.commit()
    db.refresh(user)
    return user


def suspend_user(db: Session, admin: User, user_id: uuid.UUID, reason: str | None) -> User:
    user = _target_user(db, user_id)
    if not reason or len(reason.strip()) < 3:
        raise ValidationAppError("A suspension reason is required.")
    if user.account_status is AccountStatus.SUSPENDED:
        raise ConflictError("This account is already suspended.")

    user.account_status = AccountStatus.SUSPENDED
    user.suspension_reason = reason.strip()

    # An active journey cannot continue under a suspended account.
    for ride in db.scalars(
        select(Ride).where(
            Ride.driver_id == user.id,
            Ride.status.in_([RideStatus.OPEN, RideStatus.MATCHED]),
        )
    ):
        ride_service.cancel_ride(db, ride, admin, f"Account suspended: {reason}", as_admin=True)

    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.SUSPEND_USER,
        target_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        notes=reason,
    )
    create_notification_from_template(
        db,
        user_id=user.id,
        template="ACCOUNT_SUSPENDED",
        commit=False,
        reason=reason.strip(),
    )
    db.commit()
    db.refresh(user)
    return user


def issue_password_reset_code(db: Session, user_id: uuid.UUID) -> tuple[str, datetime]:
    """Fallback for when email is not configured: the admin hands the code to the member.

    The member enters it on the "Reset password" screen. It is single-use and expires
    after PASSWORD_RESET_TOKEN_MINUTES, exactly like the emailed link.
    """
    from app.services import auth_service

    user = _target_user(db, user_id)
    if user.account_status is not AccountStatus.ACTIVE:
        raise ConflictError("Reactivate this account before issuing a password reset code.")
    return auth_service.issue_password_reset_token(db, user)


def reactivate_user(db: Session, admin: User, user_id: uuid.UUID, note: str | None = None) -> User:
    user = _target_user(db, user_id)
    if user.account_status is AccountStatus.ACTIVE:
        raise ConflictError("This account is already active.")

    user.account_status = AccountStatus.ACTIVE
    user.suspension_reason = None
    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.REACTIVATE_USER,
        target_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        notes=note,
    )
    create_notification_from_template(db, user_id=user.id, template="ACCOUNT_REACTIVATED", commit=False)
    db.commit()
    db.refresh(user)
    return user


# ------------------------------------------------------------------ verifications
def _verification_row(row: Verification) -> AdminVerificationRow:
    return AdminVerificationRow(
        id=row.id,
        user_id=row.user_id,
        user_name=row.user.full_name if row.user else "Unknown member",
        user_email=row.user.email if row.user else "",
        department=row.user.department if row.user else "",
        university_id=row.user.university_id if row.user else "",
        verification_type=str(row.verification_type),
        status=row.status,
        submitted_value=row.submitted_value,
        document_url=row.document_url,
        document_asset_id=row.document_asset_id,
        review_note=row.review_note,
        reviewed_at=_aware(row.reviewed_at),
        created_at=_aware(row.created_at),
    )


def list_verifications(
    db: Session, *, status: VerificationStatus | None = None, page: int = 1, limit: int = 20
) -> tuple[list[AdminVerificationRow], int, int]:
    query = select(Verification).options(joinedload(Verification.user))
    if status is not None:
        query = query.where(Verification.status == status)
    query = query.order_by(Verification.created_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    return [_verification_row(row) for row in rows], total, pages


# ---------------------------------------------------------------------- vehicles
def _vehicle_row(vehicle: Vehicle) -> AdminVehicleRow:
    return AdminVehicleRow(
        id=vehicle.id,
        owner_id=vehicle.owner_id,
        owner_name=vehicle.owner.full_name if vehicle.owner else "Unknown member",
        vehicle_type=vehicle.vehicle_type,
        make_and_model=vehicle.make_and_model,
        color=vehicle.color,
        registration_number=vehicle.registration_number,
        passenger_capacity=vehicle.passenger_capacity,
        vehicle_photo_url=vehicle.vehicle_photo_url,
        photo_asset_id=vehicle.photo_asset_id,
        registration_asset_id=vehicle.registration_asset_id,
        status=vehicle.status,
        review_note=vehicle.review_note,
        reviewed_at=_aware(vehicle.reviewed_at),
        created_at=_aware(vehicle.created_at),
    )


def list_vehicles(
    db: Session,
    *,
    status: VehicleStatus | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminVehicleRow], int, int]:
    query = (
        select(Vehicle)
        .options(joinedload(Vehicle.owner))
        .where(Vehicle.deleted_at.is_(None))
    )
    if status is not None:
        query = query.where(Vehicle.status == status)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            or_(
                Vehicle.registration_number.ilike(like),
                Vehicle.make_and_model.ilike(like),
                Vehicle.owner.has(User.full_name.ilike(like)),
            )
        )
    query = query.order_by(Vehicle.created_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    return [_vehicle_row(row) for row in rows], total, pages


def review_vehicle(
    db: Session, admin: User, vehicle_id: uuid.UUID, *, approve: bool, note: str | None
) -> AdminVehicleRow:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.deleted_at is not None:
        raise NotFoundError("This vehicle could not be found.")
    if approve and vehicle.status is VehicleStatus.VERIFIED:
        raise ConflictError("This vehicle is already verified.")
    if not approve and not note:
        raise ValidationAppError("Explain why the vehicle was rejected.")

    vehicle.status = VehicleStatus.VERIFIED if approve else VehicleStatus.REJECTED
    vehicle.reviewed_by_id = admin.id
    vehicle.reviewed_at = utcnow()
    vehicle.review_note = note

    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.VERIFY_VEHICLE if approve else AdminActionType.REJECT_VEHICLE,
        target_user_id=vehicle.owner_id,
        entity_type="vehicle",
        entity_id=vehicle.id,
        notes=note,
    )
    create_notification_from_template(
        db,
        user_id=vehicle.owner_id,
        template="VEHICLE_VERIFIED" if approve else "VEHICLE_REJECTED",
        commit=False,
        vehicle=f"{vehicle.make_and_model} ({vehicle.registration_number})",
        reason=note or "No reason given",
    )
    db.commit()
    db.refresh(vehicle)
    return _vehicle_row(vehicle)


# ------------------------------------------------------------------------- rides
def _ride_row(ride: Ride) -> AdminRideRow:
    matched = None
    for trip in ride.trips or []:
        if str(trip.status) != "CANCELLED":
            matched = trip.passenger.full_name if trip.passenger else None
            break
    return AdminRideRow(
        id=ride.id,
        driver_id=ride.driver_id,
        driver_name=ride.driver.full_name if ride.driver else "Unknown driver",
        direction=ride.direction,
        pickup_area=ride.pickup_area,
        destination_area=ride.destination_area,
        departure_at=_aware(ride.departure_at),
        status=ride.status,
        seats_remaining=ride.seats_remaining,
        fuel_preference=str(ride.fuel_preference),
        matched_passenger_name=matched,
        requests_count=int(
            sum(1 for request in ride.requests if str(request.status) == "PENDING")
        ),
        created_at=_aware(ride.created_at),
    )


def list_rides(
    db: Session,
    *,
    status: RideStatus | None = None,
    direction: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    driver_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminRideRow], int, int]:
    query = (
        select(Ride)
        .options(joinedload(Ride.driver), selectinload(Ride.trips).joinedload(Trip.passenger), selectinload(Ride.requests))
        .where(Ride.deleted_at.is_(None))
    )
    if status is not None:
        query = query.where(Ride.status == status)
    if direction:
        query = query.where(Ride.direction == direction)
    if driver_id is not None:
        query = query.where(Ride.driver_id == driver_id)
    if date_from is not None:
        query = query.where(Ride.departure_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to is not None:
        query = query.where(Ride.departure_at <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            or_(Ride.pickup_area.ilike(like), Ride.destination_area.ilike(like), Ride.driver.has(User.full_name.ilike(like)))
        )
    query = query.order_by(Ride.departure_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    return [_ride_row(row) for row in rows], total, pages


def cancel_ride(db: Session, admin: User, ride_id: uuid.UUID, reason: str | None) -> AdminRideRow:
    ride = db.get(Ride, ride_id)
    if ride is None or ride.deleted_at is not None:
        raise NotFoundError("This journey could not be found.")
    ride_service.cancel_ride(db, ride, admin, reason or "Cancelled by an administrator", as_admin=True)
    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.CANCEL_RIDE,
        target_user_id=ride.driver_id,
        entity_type="ride",
        entity_id=ride.id,
        notes=reason,
    )
    db.commit()
    db.refresh(ride)
    return _ride_row(ride)


# ------------------------------------------------------------------------- trips
def _trip_row(trip: Trip) -> AdminTripRow:
    ride = trip.ride
    return AdminTripRow(
        id=trip.id,
        ride_id=trip.ride_id,
        driver_id=trip.driver_id,
        driver_name=trip.driver.full_name if trip.driver else "Unknown driver",
        passenger_id=trip.passenger_id,
        passenger_name=trip.passenger.full_name if trip.passenger else "Unknown passenger",
        status=trip.status,
        pickup_area=ride.pickup_area if ride is not None else None,
        destination_area=ride.destination_area if ride is not None else None,
        departure_at=_aware(ride.departure_at) if ride is not None else None,
        started_at=_aware(trip.started_at),
        completed_at=_aware(trip.completed_at),
        created_at=_aware(trip.created_at),
    )


def list_trips(
    db: Session,
    *,
    status: TripStatus | None = None,
    active_only: bool = False,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminTripRow], int, int]:
    query = select(Trip).options(
        joinedload(Trip.driver), joinedload(Trip.passenger), joinedload(Trip.ride)
    )
    if status is not None:
        query = query.where(Trip.status == status)
    if active_only:
        query = query.where(Trip.status.in_([TripStatus.CONFIRMED, TripStatus.IN_PROGRESS]))
    query = query.order_by(Trip.created_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    return [_trip_row(row) for row in rows], total, pages


# ----------------------------------------------------------------------- reports
def _report_row(report: Report) -> AdminReportRow:
    return AdminReportRow(
        id=report.id,
        reporter_id=report.reporter_id,
        reporter_name=report.reporter.full_name if report.reporter else "Unknown",
        reported_user_id=report.reported_user_id,
        reported_user_name=report.reported_user.full_name if report.reported_user else "Unknown",
        category=report.category,
        description=report.description,
        status=report.status,
        photo_reason=report.photo_reason,
        reported_photo_url=(
            f"{settings.API_V1_PREFIX}/media/{report.reported_photo_asset_id}"
            if report.reported_photo_asset_id
            else None
        ),
        ride_id=report.ride_id,
        trip_id=report.trip_id,
        resolution_note=report.resolution_note,
        resolved_at=_aware(report.resolved_at),
        created_at=_aware(report.created_at),
    )


def list_reports(
    db: Session,
    *,
    status: ReportStatus | None = None,
    category: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminReportRow], int, int]:
    query = select(Report).options(
        joinedload(Report.reporter), joinedload(Report.reported_user)
    )
    if status is not None:
        query = query.where(Report.status == status)
    if category:
        query = query.where(Report.category == category)
    query = query.order_by(Report.created_at.desc())
    rows, total, pages = _paginate(db, query, page, limit)
    return [_report_row(row) for row in rows], total, pages


def get_report(db: Session, report_id: uuid.UUID) -> AdminReportRow:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("This report could not be found.")
    return _report_row(report)


def update_report(
    db: Session,
    admin: User,
    report_id: uuid.UUID,
    *,
    status: ReportStatus,
    resolution_note: str | None,
    remove_photo: bool = False,
) -> AdminReportRow:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("This report could not be found.")
    if status in (ReportStatus.RESOLVED, ReportStatus.DISMISSED) and not resolution_note:
        raise ValidationAppError("Add a short note explaining the decision.")
    if remove_photo and report.category is not ReportCategory.PROFILE_PHOTO:
        raise ValidationAppError("Only a photo report can remove a profile photo.")

    report.status = status
    report.handled_by_id = admin.id
    report.resolution_note = resolution_note
    report.resolved_at = utcnow() if status in (ReportStatus.RESOLVED, ReportStatus.DISMISSED) else None

    if status in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        create_notification_from_template(
            db,
            user_id=report.reporter_id,
            template="REPORT_RESOLVED",
            commit=False,
            data={"report_id": str(report.id)},
            reported_name=report.reported_user.full_name.split(" ")[0],
            status=status.value.replace("_", " ").lower(),
            note=resolution_note or "",
        )

    if remove_photo:
        # Take the picture down in the same decision. The reported asset itself is
        # evidence: `clear_profile_photo` keeps a file that a report names.
        from app.services import media_service

        member = db.get(User, report.reported_user_id)
        if member is not None and media_service.clear_profile_photo(db, member):
            create_notification_from_template(
                db, user_id=member.id, template="PHOTO_REMOVED", commit=False
            )
            _log_action(
                db,
                admin=admin,
                action_type=AdminActionType.REMOVE_PROFILE_PHOTO,
                target_user_id=member.id,
                report_id=report.id,
                entity_type="report",
                entity_id=report.id,
                notes=(resolution_note or "")[:200],
            )

    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.UPDATE_REPORT,
        target_user_id=report.reported_user_id,
        report_id=report.id,
        entity_type="report",
        entity_id=report.id,
        notes=f"{status}: {resolution_note or ''}".strip(),
    )
    db.commit()
    db.refresh(report)
    return _report_row(report)


# -------------------------------------------------------------- review moderation
def _review_row(review: Review, reported_trip_ids: set[uuid.UUID]) -> AdminReviewRow:
    return AdminReviewRow(
        id=review.id,
        trip_id=review.trip_id,
        rating=review.rating,
        comment=review.comment,
        author_id=review.author_id,
        author_name=review.author.full_name,
        subject_id=review.subject_id,
        subject_name=review.subject.full_name,
        is_hidden=review.is_hidden,
        created_at=review.created_at,
        has_report=review.trip_id in reported_trip_ids,
    )


def list_reviews(
    db: Session,
    *,
    hidden: bool | None = None,
    search: str | None = None,
    min_rating: int | None = None,
    max_rating: int | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminReviewRow], int, int]:
    """Moderation feed: every review, including hidden ones."""

    query: Select = select(Review)
    if hidden is not None:
        query = query.where(Review.is_hidden.is_(hidden))
    if min_rating is not None:
        query = query.where(Review.rating >= min_rating)
    if max_rating is not None:
        query = query.where(Review.rating <= max_rating)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Review.comment).like(pattern),
                Review.author_id.in_(select(User.id).where(func.lower(User.full_name).like(pattern))),
                Review.subject_id.in_(select(User.id).where(func.lower(User.full_name).like(pattern))),
            )
        )

    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.options(joinedload(Review.author), joinedload(Review.subject))
        .order_by(Review.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    trip_ids = [review.trip_id for review in rows]
    reported_trip_ids: set[uuid.UUID] = set()
    if trip_ids:
        reported_trip_ids = set(
            db.scalars(select(Report.trip_id).where(Report.trip_id.in_(trip_ids))).all()
        )
    pages = max(1, -(-total // limit))
    return [_review_row(review, reported_trip_ids) for review in rows], total, pages


def moderate_review(
    db: Session, admin: User, review_id: uuid.UUID, *, hidden: bool, note: str | None
) -> AdminReviewRow:
    """Hide or restore a review; the subject's rating average is recomputed."""

    review = review_service.set_review_hidden(db, review_id, hidden)
    _log_action(
        db,
        admin=admin,
        action_type=AdminActionType.HIDE_REVIEW if hidden else AdminActionType.UNHIDE_REVIEW,
        target_user_id=review.author_id,
        entity_type="review",
        entity_id=review.id,
        notes=note,
    )
    db.commit()
    db.refresh(review)
    has_report = bool(db.scalar(select(Report.id).where(Report.trip_id == review.trip_id)))
    return _review_row(review, {review.trip_id} if has_report else set())


# ----------------------------------------------------------------- admin audit
def list_admin_actions(
    db: Session, *, page: int = 1, limit: int = 30
) -> tuple[list[AdminActionRow], int, int]:
    query = (
        select(AdminAction)
        .options(joinedload(AdminAction.admin))
        .order_by(AdminAction.created_at.desc())
    )
    rows, total, pages = _paginate(db, query, page, limit)

    target_ids = [row.target_user_id for row in rows if row.target_user_id]
    targets = {
        user.id: user.full_name
        for user in db.scalars(select(User).where(User.id.in_(target_ids or [uuid.uuid4()]))).all()
    }
    return (
        [
            AdminActionRow(
                id=row.id,
                admin_id=row.admin_id,
                admin_name=row.admin.full_name if row.admin else None,
                action_type=row.action_type,
                target_user_id=row.target_user_id,
                target_user_name=targets.get(row.target_user_id) if row.target_user_id else None,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                notes=row.notes,
                created_at=_aware(row.created_at),
            )
            for row in rows
        ],
        total,
        pages,
    )


# ---------------------------------------------------------------------- settings
def _maps_ready(db: Session | None) -> bool:
    """True when the app can actually draw a map right now (live console setting, §13)."""
    if db is None:
        return True
    from app.services import map_service

    try:
        config = map_service.get_config(db)
    except Exception:
        return True
    return config.enabled and (not config.needs_key or config.has_key)


def get_settings(db: Session | None = None) -> SettingsOut:
    from app import __version__

    return SettingsOut(
        environment=settings.ENVIRONMENT,
        university_domains=settings.university_domains,
        auto_verify_university_emails=settings.AUTO_VERIFY_UNIVERSITY_EMAILS,
        maps_configured=_maps_ready(db),
        smtp_configured=settings.smtp_configured,
        expo_push_enabled=settings.EXPO_PUSH_ENABLED,
        rate_limit_enabled=settings.RATE_LIMIT_ENABLED,
        admin_bootstrap_enabled=settings.ADMIN_BOOTSTRAP_ENABLED,
        max_confirmed_passengers=settings.MAX_CONFIRMED_PASSENGERS,
        ride_auto_expire_grace_minutes=settings.RIDE_AUTO_EXPIRE_GRACE_MINUTES,
        maintenance_interval_minutes=settings.MAINTENANCE_INTERVAL_MINUTES,
        api_version=__version__,
        features={
            "maps": _maps_ready(db),
            "email_delivery": settings.smtp_configured,
            "push_notifications": settings.EXPO_PUSH_ENABLED,
            "rate_limiting": settings.RATE_LIMIT_ENABLED,
            "maintenance_scheduler": settings.MAINTENANCE_INTERVAL_MINUTES > 0,
        },
    )


def media_overview(db: Session) -> dict[str, object]:
    """Storage numbers for GET /admin/media (runbook §9)."""
    from app.services.media_service import storage_stats

    stats = storage_stats(db)
    return {
        "files": stats.files,
        "bytes": stats.bytes,
        "orphans": stats.orphans,
        "orphan_bytes": stats.orphan_bytes,
        "oldest": _aware(stats.oldest),
        "retention_days": settings.MEDIA_ORPHAN_RETENTION_DAYS,
        "max_upload_bytes": settings.MAX_UPLOAD_BYTES,
    }
