"""Admin console contracts (§16).

Every list endpoint is **page-numbered** (not cursor-based) because an operations
table needs a total and a "page 3 of 12" affordance — the opposite trade-off to
the member-facing infinite feeds.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from app.models.enums import (
    AccountStatus,
    AdminActionType,
    ReportCategory,
    ReportStatus,
    RideDirection,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


# ------------------------------------------------------------------- dashboard
class TrendPoint(BaseModel):
    day: date
    count: int


class DashboardStats(BaseModel):
    total_users: int
    verified_users: int
    pending_verifications: int
    pending_vehicles: int
    suspended_accounts: int
    published_rides: int
    open_rides: int
    active_trips: int
    completed_trips: int
    open_reports: int
    rides_today: int
    trips_today: int


class DashboardOut(BaseModel):
    stats: DashboardStats
    users_per_day: list[TrendPoint]
    rides_per_day: list[TrendPoint]
    trips_per_day: list[TrendPoint]
    rides_by_status: dict[str, int]
    trips_by_status: dict[str, int]
    generated_at: datetime


class AnalyticsOut(BaseModel):
    days: int
    completion_rate: float
    cancellation_rate: float
    average_rating: float
    fuel_split: dict[str, int]
    vehicle_split: dict[str, int]
    direction_split: dict[str, int]
    top_pickup_areas: list[dict[str, Any]]
    top_destinations: list[dict[str, Any]]
    users_per_day: list[TrendPoint]
    rides_per_day: list[TrendPoint]


# ----------------------------------------------------------------------- users
class AdminPasswordResetCodeOut(BaseModel):
    code: str
    expires_at: datetime
    expires_in_minutes: int


class AdminUserRow(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str
    role: UserRole
    department: str
    university_id: str
    verification_status: VerificationStatus
    account_status: AccountStatus
    rating_average: float
    rating_count: int
    completed_trips_count: int
    vehicles_count: int = 0
    # Phase 13: the reviewer sees the same face the community sees.
    profile_photo_url: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class AdminVehicleRow(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    owner_name: str
    vehicle_type: VehicleType
    make_and_model: str
    color: str
    registration_number: str
    passenger_capacity: int
    vehicle_photo_url: str | None = None
    photo_asset_id: uuid.UUID | None = None
    registration_asset_id: uuid.UUID | None = None
    status: VehicleStatus
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AdminRideRow(BaseModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    driver_name: str
    direction: RideDirection
    pickup_area: str
    destination_area: str
    departure_at: datetime
    status: RideStatus
    seats_remaining: int
    fuel_preference: str
    matched_passenger_name: str | None = None
    requests_count: int = 0
    created_at: datetime


class AdminTripRow(BaseModel):
    id: uuid.UUID
    ride_id: uuid.UUID
    driver_id: uuid.UUID
    driver_name: str
    passenger_id: uuid.UUID
    passenger_name: str
    status: TripStatus
    pickup_area: str | None = None
    destination_area: str | None = None
    departure_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class AdminReportRow(BaseModel):
    id: uuid.UUID
    reporter_id: uuid.UUID
    reporter_name: str
    reported_user_id: uuid.UUID
    reported_user_name: str
    category: ReportCategory
    description: str
    status: ReportStatus
    # Phase 15 — present only on photo reports.
    photo_reason: str | None = None
    reported_photo_url: str | None = None
    ride_id: uuid.UUID | None = None
    trip_id: uuid.UUID | None = None
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class MediaOverviewOut(BaseModel):
    """Storage health for uploaded documents (§16, Phase 10)."""

    files: int
    bytes: int
    orphans: int
    orphan_bytes: int
    oldest: datetime | None = None
    retention_days: int
    max_upload_bytes: int


class AdminVerificationRow(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    department: str
    university_id: str
    verification_type: str
    status: VerificationStatus
    submitted_value: str | None = None
    document_url: str | None = None
    document_asset_id: uuid.UUID | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AdminUserDetail(BaseModel):
    user: AdminUserRow
    email_verified_at: datetime | None = None
    verified_at: datetime | None = None
    suspension_reason: str | None = None
    home_area: str | None = None
    semester: int | None = None
    vehicles: list[AdminVehicleRow] = Field(default_factory=list)
    recent_rides: list[AdminRideRow] = Field(default_factory=list)
    verifications: list[AdminVerificationRow] = Field(default_factory=list)
    trips_as_driver: int = 0
    trips_as_passenger: int = 0
    reports_against: int = 0
    reports_filed: int = 0


class AdminActionRow(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID | None = None
    admin_name: str | None = None
    action_type: AdminActionType
    target_user_id: uuid.UUID | None = None
    target_user_name: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime


# ------------------------------------------------------------------- mutations
class AdminReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class ReportUpdateIn(BaseModel):
    status: Literal["OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]
    resolution_note: str | None = Field(default=None, max_length=1000)
    # Phase 15: resolving a photo report can also take the picture down in one step.
    remove_photo: bool = Field(
        default=False, description="Also remove the reported member's current profile photo"
    )


class AdminReviewRow(BaseModel):
    """A review as the moderation view sees it — including hidden ones."""

    id: uuid.UUID
    trip_id: uuid.UUID
    rating: int
    comment: str | None = None
    author_id: uuid.UUID
    author_name: str
    subject_id: uuid.UUID
    subject_name: str
    is_hidden: bool
    created_at: datetime
    #: True when a report exists for this trip, so the reviewer sees the context.
    has_report: bool = False


class SettingsOut(BaseModel):
    """Read-only view of the effective runtime configuration (§17)."""

    environment: str
    university_domains: list[str]
    auto_verify_university_emails: bool
    maps_configured: bool
    smtp_configured: bool
    expo_push_enabled: bool
    rate_limit_enabled: bool
    admin_bootstrap_enabled: bool
    max_confirmed_passengers: int
    ride_auto_expire_grace_minutes: int
    maintenance_interval_minutes: int
    api_version: str
    features: dict[str, bool]
