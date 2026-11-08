"""Reports & complaints (§15).

A member can report another member, optionally attached to the trip or ride where
it happened. The service is deliberately strict about **who** may be reported:

* you cannot report yourself;
* when a `trip_id` is supplied, the reported member must be the other participant
  of that trip (the API derives it if the client omits it);
* when a `ride_id` is supplied, the reported member must be the driver or somebody
  who actually requested that ride;
* one *open* report per reporter→subject pair at a time, so the queue cannot be
  flooded (a second report after the first is resolved is allowed);
* the reporter gets an acknowledgement, and every admin gets a system
  notification — the queue is never silent.

Reports are **never** deleted by the reporter. The office resolves or dismisses
them, and the reporter is told the outcome (see `admin_service.update_report`).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.enums import (
    PHOTO_REPORT_REASON_LABELS,
    AccountStatus,
    ReportCategory,
    ReportStatus,
    UserRole,
)
from app.models.report import Report
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import User
from app.schemas.report import PhotoReportIn, ReportIn, ReportOut, ReportPage, ReportSubjectOut
from app.services.notification_service import create_notification_from_template

logger = logging.getLogger("ssuet.rideshare.reports")


def _subject_out(user: User) -> ReportSubjectOut:
    return ReportSubjectOut(
        id=user.id,
        full_name=user.full_name,
        profile_photo_url=user.photo_url,
        role=user.role,
        department=user.department,
    )


def _report_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        category=report.category,
        description=report.description,
        status=report.status,
        reported_user=_subject_out(report.reported_user),
        trip_id=report.trip_id,
        ride_id=report.ride_id,
        resolution_note=report.resolution_note,
        resolved_at=report.resolved_at,
        created_at=report.created_at,
    )


def _resolve_target(
    db: Session, reporter: User, payload: ReportIn
) -> tuple[User, uuid.UUID | None, uuid.UUID | None]:
    """Work out who is being reported, and validate the claimed context."""

    trip_id = payload.trip_id
    ride_id = payload.ride_id
    target: User | None = None

    if trip_id is not None:
        trip = db.get(Trip, trip_id)
        if trip is None:
            raise NotFoundError("This trip could not be found.")
        if not trip.involves(reporter.id):
            raise ForbiddenError("You were not part of this trip.")
        counterpart = trip.passenger if reporter.id == trip.driver_id else trip.driver
        if payload.reported_user_id is not None and payload.reported_user_id != counterpart.id:
            raise ValidationAppError(
                "The member you are reporting is not the other participant of this trip."
            )
        target = counterpart
        ride_id = ride_id or trip.ride_id

    elif ride_id is not None:
        ride = db.get(Ride, ride_id)
        if ride is None:
            raise NotFoundError("This ride could not be found.")
        participant_ids = {ride.driver_id}
        participant_ids.update(
            db.scalars(
                select(RideRequest.passenger_id).where(RideRequest.ride_id == ride_id)
            ).all()
        )
        if reporter.id not in participant_ids:
            raise ForbiddenError("You were not part of this ride.")
        if payload.reported_user_id is None:
            if ride.driver_id == reporter.id:
                raise ValidationAppError("Tell us which passenger you are reporting.")
            target = db.get(User, ride.driver_id)
        else:
            if payload.reported_user_id not in participant_ids:
                raise ValidationAppError(
                    "The member you are reporting was not part of this ride."
                )
            target = db.get(User, payload.reported_user_id)

    elif payload.reported_user_id is not None:
        target = db.get(User, payload.reported_user_id)

    if target is None:
        raise NotFoundError("This member could not be found.")
    if target.id == reporter.id:
        raise ValidationAppError("You cannot report yourself.")
    if target.account_status is AccountStatus.DEACTIVATED and target.role is UserRole.ADMIN:
        raise ValidationAppError("This account cannot be reported.")

    return target, trip_id, ride_id


def create_report(db: Session, reporter: User, payload: ReportIn) -> ReportOut:
    target, trip_id, ride_id = _resolve_target(db, reporter, payload)

    open_report = db.scalar(
        select(Report).where(
            Report.reporter_id == reporter.id,
            Report.reported_user_id == target.id,
            Report.status == ReportStatus.OPEN,
        )
    )
    if open_report is not None:
        raise ConflictError(
            "You already have an open report about this member. "
            "The ride-share office will respond to it first."
        )

    report = Report(
        reporter_id=reporter.id,
        reported_user_id=target.id,
        trip_id=trip_id,
        ride_id=ride_id,
        category=payload.category,
        description=" ".join(payload.description.split()),
        status=ReportStatus.OPEN,
    )
    db.add(report)
    db.flush()

    create_notification_from_template(
        db,
        user_id=reporter.id,
        template="REPORT_RECEIVED",
        commit=False,
        data={"report_id": str(report.id)},
        reported_name=target.full_name.split(" ")[0],
    )

    # Tell the office. Notifications are persisted rows, so this is also the audit
    # trail the dashboard shows in the members' history.
    admins = db.scalars(
        select(User).where(User.role == UserRole.ADMIN, User.account_status == AccountStatus.ACTIVE)
    ).all()
    for admin in admins:
        create_notification_from_template(
            db,
            user_id=admin.id,
            template="ADMIN_NEW_REPORT",
            commit=False,
            data={"report_id": str(report.id)},
            reporter_name=reporter.full_name,
            reported_name=target.full_name,
            category=payload.category.value,
        )

    db.commit()
    db.refresh(report)
    logger.info("report %s filed by %s against %s", report.id, reporter.id, target.id)
    return _report_out(report)


def create_photo_report(
    db: Session, reporter: User, target_user_id: uuid.UUID, payload: PhotoReportIn
) -> ReportOut:
    """File a complaint about a member's profile photo (Phase 15).

    The reported asset is pinned on the report, so the evidence survives the member
    uploading something else — `media_service.set_profile_photo` refuses to delete a
    reported file for exactly this reason.
    """
    from app.services import media_service

    target = db.get(User, target_user_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError("This member could not be found.")
    if target.id == reporter.id:
        raise ValidationAppError("To change your own photo, upload another one.")

    asset = media_service.profile_photo_asset(db, target)
    if asset is None:
        raise NotFoundError("This member has not set a profile photo.")

    open_report = db.scalar(
        select(Report).where(
            Report.reporter_id == reporter.id,
            Report.reported_user_id == target.id,
            Report.category == ReportCategory.PROFILE_PHOTO,
            Report.status == ReportStatus.OPEN,
        )
    )
    if open_report is not None:
        raise ConflictError(
            "You already have an open report about this member's photo. "
            "The ride-share office will respond to it first."
        )

    report = Report(
        reporter_id=reporter.id,
        reported_user_id=target.id,
        category=ReportCategory.PROFILE_PHOTO,
        photo_reason=payload.reason.value,
        description=" ".join(payload.description.split()),
        reported_photo_asset_id=asset.id,
        status=ReportStatus.OPEN,
    )
    db.add(report)
    db.flush()

    create_notification_from_template(
        db,
        user_id=reporter.id,
        template="REPORT_RECEIVED",
        commit=False,
        data={"report_id": str(report.id)},
        reported_name=target.full_name.split(" ")[0],
    )
    reason_label = PHOTO_REPORT_REASON_LABELS.get(payload.reason.value, payload.reason.value)
    for admin in db.scalars(
        select(User).where(User.role == UserRole.ADMIN, User.account_status == AccountStatus.ACTIVE)
    ).all():
        create_notification_from_template(
            db,
            user_id=admin.id,
            template="ADMIN_NEW_PHOTO_REPORT",
            commit=False,
            data={"report_id": str(report.id)},
            reporter_name=reporter.full_name,
            reported_name=target.full_name,
            reason=reason_label,
        )

    db.commit()
    db.refresh(report)
    logger.info(
        "photo report %s filed by %s against %s (asset %s)",
        report.id,
        reporter.id,
        target.id,
        asset.id,
    )
    return _report_out(report)


# ----------------------------------------------------------------------- read
def list_my_reports(
    db: Session,
    reporter: User,
    *,
    status: ReportStatus | None = None,
    page: int = 1,
    limit: int = 20,
) -> ReportPage:
    base = select(Report).where(Report.reporter_id == reporter.id)
    if status is not None:
        base = base.where(Report.status == status)

    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(
        base.options(joinedload(Report.reported_user))
        .order_by(Report.created_at.desc(), Report.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    return ReportPage(
        items=[_report_out(report) for report in rows],
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
    )


def get_my_report(db: Session, reporter: User, report_id: uuid.UUID) -> ReportOut:
    report = db.get(Report, report_id)
    if report is None or report.reporter_id != reporter.id:
        # Same answer either way: a member never learns that another member's
        # report id exists.
        raise NotFoundError("This report could not be found.")
    return _report_out(report)


def count_open_reports(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Report).where(Report.status == ReportStatus.OPEN)
        )
        or 0
    )
