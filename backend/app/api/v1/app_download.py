"""Public APK download link for the web app, plus the admin write path (no redeploy needed)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import DbSession
from app.services import app_download_service as svc

router = APIRouter(prefix="/app", tags=["App download"])


class AppDownloadOut(BaseModel):
    available: bool
    url: str | None
    version: str | None
    updated_at: str | None


class AppDownloadIn(BaseModel):
    url: str = Field(default="", max_length=svc.MAX_URL_LENGTH, description="https link to the APK; empty clears it.")
    version: str = Field(default="", max_length=svc.MAX_VERSION_LENGTH)


def to_out(item: svc.AppDownload) -> AppDownloadOut:
    return AppDownloadOut(
        available=item.available, url=item.url, version=item.version, updated_at=item.updated_at
    )


@router.get("/download", response_model=AppDownloadOut, summary="Latest Android APK link (public)")
def public_download(db: DbSession) -> AppDownloadOut:
    return to_out(svc.get_download(db))
