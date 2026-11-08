"""Admin console API — `/api/v1/admin` (§16).

Every route is guarded by `AdminUser` (JWT **and** `role=ADMIN` re-checked from the
database), and every mutation records an `admin_actions` row plus notifies the
affected member. The dashboard never computes statistics locally: all numbers come
from these endpoints.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminUser, DbSession
from app.core.config import settings
from app.api.v1.app_download import AppDownloadOut, to_out as _app_download_out
from app.models.enums import (
    AccountStatus,
    AdminActionType,
    ReportStatus,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
    VerificationStatus,
)
from app.services import app_download_service
from app.schemas.admin import (
    AdminActionRow,
    AdminReasonIn,
    AdminReportRow,
    MediaOverviewOut,
    AdminReviewRow,
    AdminRideRow,
    AdminTripRow,
    AdminUserDetail,
    AdminPasswordResetCodeOut,
    AdminUserRow,
    AdminVehicleRow,
    AdminVerificationRow,
    AnalyticsOut,
    DashboardOut,
    Page,
    ReportUpdateIn,
    SettingsOut,
)
from app.schemas.common import MessageOut
from app.schemas.maps import AdminMapSettingsIn, AdminMapSettingsOut, MapTestOut
from app.services import admin_service, map_service, system_service

router = APIRouter(prefix="/admin", tags=["Admin"])


def _page(items: list, total: int, page: int, limit: int, pages: int) -> dict:
    return {"items": items, "total": total, "page": page, "limit": limit, "pages": pages}


# ----------------------------------------------------------------- dashboard
@router.get("/dashboard", response_model=DashboardOut, summary="Stat cards + trend series")
def dashboard(current_admin: AdminUser, db: DbSession) -> DashboardOut:
    return admin_service.dashboard(db)


@router.get("/analytics", response_model=AnalyticsOut, summary="Recharts-ready aggregates")
def analytics(
    current_admin: AdminUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=180),
) -> AnalyticsOut:
    return admin_service.analytics(db, days=days)


@router.get(
    "/health",
    summary="Deep health for the operations panel",
    description=(
        "Database latency and schema revision, the sizes of the review queues, media "
        "storage and free disk, the last housekeeping run, and any warnings. Unlike "
        "`/health`, this is for a person, not a load balancer — it costs a few counts "
        "and is therefore admin-only."
    ),
)
def health_panel(current_admin: AdminUser, db: DbSession) -> dict:
    return system_service.health_report(db)


@router.get(
    "/media",
    response_model=MediaOverviewOut,
    summary="Uploaded-document storage overview",
    description=(
        "File count, total bytes, and how many uploads are currently orphaned (not "
        "referenced by any verification or vehicle). Orphans older than "
        "`MEDIA_ORPHAN_RETENTION_DAYS` are removed by the housekeeping sweep."
    ),
)
def media_overview(current_admin: AdminUser, db: DbSession) -> MediaOverviewOut:
    return MediaOverviewOut(**admin_service.media_overview(db))


# --------------------------------------------------------------- integrations
@router.get(
    "/integrations/maps",
    response_model=AdminMapSettingsOut,
    summary="Map provider configuration",
    description=(
        "Shows the provider in use and whether a credential is stored — never the key itself. "
        "Rotating the key here takes effect on the next tile request: no app rebuild, no redeploy."
    ),
)
def map_integration(current_admin: AdminUser, db: DbSession) -> AdminMapSettingsOut:
    return AdminMapSettingsOut(**map_service.admin_settings_row(db))


@router.put(
    "/integrations/maps",
    response_model=AdminMapSettingsOut,
    summary="Change map provider, style, or API key",
)
def update_map_integration(
    payload: AdminMapSettingsIn, current_admin: AdminUser, db: DbSession
) -> AdminMapSettingsOut:
    try:
        map_service.update_config(
            db,
            actor=current_admin,
            provider=payload.provider,
            style=payload.style,
            api_key=payload.api_key,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        from app.core.errors import ValidationAppError

        raise ValidationAppError(str(exc)) from exc
    admin_service.record_action(
        db,
        admin=current_admin,
        action_type=AdminActionType.UPDATE_SETTINGS,
        notes=f"Map provider set to {payload.provider or 'unchanged'}"
        + (" (key updated)" if payload.api_key else ""),
    )
    return AdminMapSettingsOut(**map_service.admin_settings_row(db))


@router.post(
    "/integrations/maps/test",
    response_model=MapTestOut,
    summary="Fetch one tile to prove the credential works",
)
def test_map_integration(current_admin: AdminUser, db: DbSession) -> MapTestOut:
    return MapTestOut(**map_service.test_connection(db))


class AdminAppDownloadIn(BaseModel):
    url: str = Field(default="", max_length=500)
    version: str = Field(default="", max_length=40)


@router.get(
    "/integrations/app-download",
    response_model=AppDownloadOut,
    summary="Current Android APK link shown on the web app",
)
def app_download_integration(current_admin: AdminUser, db: DbSession) -> AppDownloadOut:
    return _app_download_out(app_download_service.get_download(db))


@router.put(
    "/integrations/app-download",
    response_model=AppDownloadOut,
    summary="Publish a new Android APK link (no redeploy)",
)
def update_app_download_integration(
    payload: AdminAppDownloadIn, current_admin: AdminUser, db: DbSession
) -> AppDownloadOut:
    try:
        item = app_download_service.update_download(
            db, actor=current_admin, url=payload.url, version=payload.version
        )
    except app_download_service.AppDownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _app_download_out(item)


@router.get("/settings", response_model=SettingsOut, summary="Effective runtime configuration (read-only)")
def settings_view(current_admin: AdminUser, db: DbSession) -> SettingsOut:
    return admin_service.get_settings(db)


# --------------------------------------------------------------------- users
@router.get("/users", response_model=Page[AdminUserRow], summary="Search and filter members")
def list_users(
    current_admin: AdminUser,
    db: DbSession,
    search: str | None = Query(default=None, description="Name, email, university id or phone"),
    role: UserRole | None = Query(default=None),
    account_status: AccountStatus | None = Query(default=None, alias="status"),
    verification: VerificationStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_users(
        db,
        search=search,
        role=role,
        status=account_status,
        verification=verification,
        page=page,
        limit=limit,
    )
    return _page(rows, total, page, limit, pages)


@router.get("/users/{user_id}", response_model=AdminUserDetail, summary="Full member dossier")
def get_user(user_id: uuid.UUID, current_admin: AdminUser, db: DbSession) -> AdminUserDetail:
    return admin_service.get_user_detail(db, user_id)


@router.post("/users/{user_id}/verify", response_model=AdminUserRow, summary="Approve verification")
def verify_user(
    user_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminUserRow:
    user = admin_service.verify_user(db, current_admin, user_id, payload.note if payload else None)
    return admin_service.user_row(db, user)


@router.post("/users/{user_id}/reject", response_model=AdminUserRow, summary="Reject verification")
def reject_user(
    user_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminUserRow:
    user = admin_service.reject_user(db, current_admin, user_id, payload.reason if payload else None)
    return admin_service.user_row(db, user)


@router.post("/users/{user_id}/suspend", response_model=AdminUserRow, summary="Suspend an account")
def suspend_user(
    user_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn,
) -> AdminUserRow:
    user = admin_service.suspend_user(db, current_admin, user_id, payload.reason)
    return admin_service.user_row(db, user)


@router.post(
    "/users/{user_id}/password-reset-code",
    response_model=AdminPasswordResetCodeOut,
    summary="Issue a one-time password reset code (use when email is not set up)",
)
def issue_password_reset_code(
    user_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
) -> AdminPasswordResetCodeOut:
    code, expires_at = admin_service.issue_password_reset_code(db, user_id)
    return AdminPasswordResetCodeOut(
        code=code,
        expires_at=expires_at,
        expires_in_minutes=settings.PASSWORD_RESET_TOKEN_MINUTES,
    )


@router.post("/users/{user_id}/reactivate", response_model=AdminUserRow, summary="Reactivate an account")
def reactivate_user(
    user_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminUserRow:
    user = admin_service.reactivate_user(db, current_admin, user_id, payload.note if payload else None)
    return admin_service.user_row(db, user)


# ------------------------------------------------------------- verifications
@router.get(
    "/verifications",
    response_model=Page[AdminVerificationRow],
    summary="Verification queue",
)
def list_verifications(
    current_admin: AdminUser,
    db: DbSession,
    verification_status: VerificationStatus | None = Query(default=VerificationStatus.PENDING, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_verifications(
        db, status=verification_status, page=page, limit=limit
    )
    return _page(rows, total, page, limit, pages)


# ------------------------------------------------------------------ vehicles
@router.get("/vehicles", response_model=Page[AdminVehicleRow], summary="Vehicle verification queue")
def list_vehicles(
    current_admin: AdminUser,
    db: DbSession,
    vehicle_status: VehicleStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_vehicles(
        db, status=vehicle_status, search=search, page=page, limit=limit
    )
    return _page(rows, total, page, limit, pages)


@router.post("/vehicles/{vehicle_id}/verify", response_model=AdminVehicleRow, summary="Approve a vehicle")
def verify_vehicle(
    vehicle_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminVehicleRow:
    return admin_service.review_vehicle(
        db, current_admin, vehicle_id, approve=True, note=payload.note if payload else None
    )


@router.post("/vehicles/{vehicle_id}/reject", response_model=AdminVehicleRow, summary="Reject a vehicle")
def reject_vehicle(
    vehicle_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn,
) -> AdminVehicleRow:
    return admin_service.review_vehicle(
        db, current_admin, vehicle_id, approve=False, note=payload.reason
    )


# --------------------------------------------------------------------- rides
@router.get("/rides", response_model=Page[AdminRideRow], summary="Published rides")
def list_rides(
    current_admin: AdminUser,
    db: DbSession,
    ride_status: RideStatus | None = Query(default=None, alias="status"),
    direction: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    driver_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_rides(
        db,
        status=ride_status,
        direction=direction,
        date_from=date_from,
        date_to=date_to,
        search=search,
        driver_id=driver_id,
        page=page,
        limit=limit,
    )
    return _page(rows, total, page, limit, pages)


@router.post("/rides/{ride_id}/cancel", response_model=AdminRideRow, summary="Force-cancel a ride")
def cancel_ride(
    ride_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminRideRow:
    return admin_service.cancel_ride(
        db, current_admin, ride_id, payload.reason if payload else None
    )


# --------------------------------------------------------------------- trips
@router.get("/trips", response_model=Page[AdminTripRow], summary="Trips (any status)")
def list_trips(
    current_admin: AdminUser,
    db: DbSession,
    trip_status: TripStatus | None = Query(default=None, alias="status"),
    active_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_trips(
        db, status=trip_status, active_only=active_only, page=page, limit=limit
    )
    return _page(rows, total, page, limit, pages)


# ------------------------------------------------------------------- reports
@router.get("/reports", response_model=Page[AdminReportRow], summary="Reports & complaints")
def list_reports(
    current_admin: AdminUser,
    db: DbSession,
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_reports(
        db, status=report_status, category=category, page=page, limit=limit
    )
    return _page(rows, total, page, limit, pages)


@router.get("/reports/{report_id}", response_model=AdminReportRow, summary="One report")
def get_report(report_id: uuid.UUID, current_admin: AdminUser, db: DbSession) -> AdminReportRow:
    return admin_service.get_report(db, report_id)


@router.patch("/reports/{report_id}", response_model=AdminReportRow, summary="Handle a report")
def update_report(
    report_id: uuid.UUID,
    payload: ReportUpdateIn,
    current_admin: AdminUser,
    db: DbSession,
) -> AdminReportRow:
    return admin_service.update_report(
        db,
        current_admin,
        report_id,
        status=ReportStatus(payload.status),
        resolution_note=payload.resolution_note,
        remove_photo=payload.remove_photo,
    )


# -------------------------------------------------------------- review moderation
@router.get(
    "/reviews",
    response_model=Page[AdminReviewRow],
    summary="Every review, including hidden ones",
)
def list_reviews(
    current_admin: AdminUser,
    db: DbSession,
    hidden: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    max_rating: int | None = Query(default=None, ge=1, le=5),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_reviews(
        db,
        hidden=hidden,
        search=search,
        min_rating=min_rating,
        max_rating=max_rating,
        page=page,
        limit=limit,
    )
    return _page(rows, total, page, limit, pages)


@router.post(
    "/reviews/{review_id}/hide",
    response_model=AdminReviewRow,
    summary="Hide an abusive review",
)
def hide_review(
    review_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminReviewRow:
    return admin_service.moderate_review(
        db, current_admin, review_id, hidden=True, note=payload.reason if payload else None
    )


@router.post(
    "/reviews/{review_id}/unhide",
    response_model=AdminReviewRow,
    summary="Restore a hidden review",
)
def unhide_review(
    review_id: uuid.UUID,
    current_admin: AdminUser,
    db: DbSession,
    payload: AdminReasonIn | None = None,
) -> AdminReviewRow:
    return admin_service.moderate_review(
        db, current_admin, review_id, hidden=False, note=payload.note if payload else None
    )


# ----------------------------------------------------------------- audit log
@router.get(
    "/admin-actions",
    response_model=Page[AdminActionRow],
    summary="Administrative action history",
)
def list_admin_actions(
    current_admin: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict:
    rows, total, pages = admin_service.list_admin_actions(db, page=page, limit=limit)
    return _page(rows, total, page, limit, pages)


@router.get("/ping", response_model=MessageOut, summary="Guard check for the console")
def ping(current_admin: AdminUser) -> MessageOut:
    return MessageOut(message="Authenticated as administrator.")
