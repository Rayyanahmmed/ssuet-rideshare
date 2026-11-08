"""Where the Android APK can be downloaded (shown on the web app).

The APK is built with EAS and hosted outside this server (for example on expo.dev). The admin
pastes the link and version here, so a new build is published without a redeploy. The link is
validated as http(s) only, because it is rendered as a button on the public web app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.models.user import User

URL_KEY = "app.android_url"
VERSION_KEY = "app.android_version"
UPDATED_KEY = "app.android_updated_at"

MAX_URL_LENGTH = 500
MAX_VERSION_LENGTH = 40


class AppDownloadError(ValueError):
    """Raised for a link that cannot be published."""


@dataclass(frozen=True)
class AppDownload:
    available: bool
    url: str | None
    version: str | None
    updated_at: str | None


def _get(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str, actor: User | None) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=actor.id if actor else None))
    else:
        row.value = value
        if actor is not None:
            row.updated_by_id = actor.id
    db.flush()


def validate_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        return ""
    if len(url) > MAX_URL_LENGTH:
        raise AppDownloadError(f"Download link must be at most {MAX_URL_LENGTH} characters.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AppDownloadError("Download link must start with https:// (or http:// for local testing).")
    return url


def get_download(db: Session) -> AppDownload:
    url = _get(db, URL_KEY) or ""
    version = _get(db, VERSION_KEY) or ""
    updated = _get(db, UPDATED_KEY) or None
    return AppDownload(
        available=bool(url),
        url=url or None,
        version=version or None,
        updated_at=updated,
    )


def update_download(db: Session, *, actor: User, url: str, version: str) -> AppDownload:
    clean_url = validate_url(url)
    clean_version = version.strip()
    if len(clean_version) > MAX_VERSION_LENGTH:
        raise AppDownloadError(f"Version must be at most {MAX_VERSION_LENGTH} characters.")
    _set(db, URL_KEY, clean_url, actor)
    _set(db, VERSION_KEY, clean_version, actor)
    _set(db, UPDATED_KEY, datetime.now(timezone.utc).isoformat(), actor)
    db.commit()
    return get_download(db)
