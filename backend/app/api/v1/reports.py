"""Reports & complaints — `/api/v1/reports` (§15).

Filing a report is a safety action, so it is rate-limited and never anonymous: the
office must be able to see who said what. Reading is restricted to the reporter —
the reported member is contacted by an administrator, not by the API.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.models.enums import ReportStatus
from app.schemas.report import ReportIn, ReportOut, ReportPage
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post(
    "",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="File a report about a member or journey",
)
@limiter.limit("5/minute")
def create_report(
    payload: ReportIn,
    request: Request,  # required by the rate limiter
    current_user: CurrentUser,
    db: DbSession,
) -> ReportOut:
    return report_service.create_report(db, current_user, payload)


@router.get("", response_model=ReportPage, summary="Reports I have filed")
def list_my_reports(
    current_user: CurrentUser,
    db: DbSession,
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> ReportPage:
    return report_service.list_my_reports(
        db, current_user, status=report_status, page=page, limit=limit
    )


@router.get("/{report_id}", response_model=ReportOut, summary="One report I filed")
def get_my_report(report_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> ReportOut:
    return report_service.get_my_report(db, current_user, report_id)
