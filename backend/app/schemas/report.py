"""Report / complaint contracts (§15).

A report always names the member it is about. When it references a trip or ride
the API derives and validates that member itself, so a client can never file a
complaint against somebody who had nothing to do with the journey.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import PhotoReportReason, ReportCategory, ReportStatus, UserRole

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 1000


class ReportIn(BaseModel):
    category: ReportCategory
    description: str = Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    reported_user_id: uuid.UUID | None = Field(
        default=None, description="Required unless trip_id/ride_id identifies the member"
    )
    trip_id: uuid.UUID | None = None
    ride_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _needs_a_target(self) -> "ReportIn":
        if self.reported_user_id is None and self.trip_id is None and self.ride_id is None:
            raise ValueError("Tell us which member or journey this report is about.")
        return self


class PhotoReportIn(BaseModel):
    """A complaint about a profile picture (Phase 15).

    Narrower than `ReportIn` on purpose: there is no trip or ride to point at, and the
    reason list is about the *picture*, so the office can triage it without reading prose.
    """

    reason: PhotoReportReason
    description: str = Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)


class ReportSubjectOut(BaseModel):
    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    role: UserRole
    department: str


class ReportOut(BaseModel):
    """What the reporter sees: their own words plus the office's decision."""

    id: uuid.UUID
    category: ReportCategory
    description: str
    status: ReportStatus
    reported_user: ReportSubjectOut
    trip_id: uuid.UUID | None = None
    ride_id: uuid.UUID | None = None
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class ReportPage(BaseModel):
    items: list[ReportOut]
    total: int
    page: int
    limit: int
    pages: int
