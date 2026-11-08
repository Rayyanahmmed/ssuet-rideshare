"""Media storage: validation, persistence and access control (§4, §16).

Design rules, in order of importance:

1. **Never trust the client.** The declared `Content-Type` and the filename are
   hints only. The bytes are sniffed (magic numbers) and a file whose bytes do not
   match an allowed image/PDF signature is rejected, even if it is named `.jpg`.
2. **Never trust the path.** Stored names are generated (`uuid4` + extension from
   the sniffed type), so `../../etc/passwd` in an upload filename cannot escape
   `MEDIA_ROOT`. The original name is kept only as a display string, sanitised.
3. **Cap while streaming.** The size limit is enforced chunk by chunk; an oversize
   upload is abandoned at the limit instead of being buffered into memory first.
4. **Serve through the API.** Files are NOT mounted as a public static directory —
   a student ID card is personal data. `GET /media/{id}` checks ownership.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.enums import UserRole
from app.models.media import (
    PURPOSE_PROFILE_PHOTO,
    PURPOSE_VERIFICATION_DOCUMENT,
    MediaAsset,
)
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.verification import Verification

logger = logging.getLogger("ssuet.rideshare.media")

CHUNK_SIZE = 64 * 1024

# magic-number → (canonical mime, extension)
SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"RIFF", "image/webp", "webp"),  # verified further: bytes 8..12 must be WEBP
    (b"%PDF-", "application/pdf", "pdf"),
]

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
# Profile pictures (Phase 13): a person's face, not a document scan.
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class PayloadTooLargeError(ValidationAppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "This file is larger than the upload limit."


def _media_root() -> Path:
    """Resolve MEDIA_ROOT lazily so tests can point it at a temp directory."""
    root = Path(settings.MEDIA_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sniff(head: bytes) -> tuple[str, str] | None:
    """Return (mime, extension) for a recognised file head, else None."""
    for magic, mime, ext in SIGNATURES:
        if not head.startswith(magic):
            continue
        if mime == "image/webp" and head[8:12] != b"WEBP":
            continue
        return mime, ext
    return None


def _safe_display_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = _UNSAFE_NAME.sub("_", Path(name).name)[:200]
    return cleaned or None


def _relative_path(ext: str) -> str:
    now = datetime.now(timezone.utc)
    return f"uploads/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.{ext}"


async def store_upload(
    db: Session,
    owner: User,
    upload: UploadFile,
    *,
    purpose: str = PURPOSE_VERIFICATION_DOCUMENT,
    max_bytes: int | None = None,
    images_only: bool = False,
    normalise: bool = False,
) -> MediaAsset:
    """Validate and persist one uploaded file, returning its `MediaAsset` row.

    `images_only` and `max_bytes` exist for the profile photo (Phase 13): a picture is
    not a document scan, so a PDF is refused and the ceiling is lower. `normalise`
    (Phase 14) goes one step further and stores a cleaned 512 px WebP instead of the
    original bytes — see `image_service`. Documents are never normalised: an
    administrator has to read them.
    """
    limit = max_bytes or settings.MAX_UPLOAD_BYTES
    allowed = IMAGE_MIME if images_only else ALLOWED_MIME
    head = await upload.read(16)
    if not head:
        raise ValidationAppError("The uploaded file is empty.")
    detected = sniff(head)
    if detected is None or detected[0] not in allowed:
        raise ValidationAppError(
            "Upload a JPG, PNG or WebP image." if images_only else "Upload a JPG, PNG, WebP or PDF file.",
            details={"allowed": sorted(allowed)},
        )
    mime, ext = detected

    declared = (upload.content_type or "").split(";")[0].strip().lower()
    if declared and declared not in allowed:
        raise ValidationAppError(
            "Upload a JPG, PNG or WebP image." if images_only else "Upload a JPG, PNG, WebP or PDF file.",
            details={"declared": declared},
        )

    oversized = PayloadTooLargeError(
        f"This file is larger than {limit / (1024 * 1024):.1f} MB."
        .replace(".0 MB", " MB")
    )

    if normalise:
        # The image is going to be re-encoded anyway, so the bytes are collected first
        # and the *processed* result is what gets stored. The original never lands.
        chunks = bytearray()
        chunk = head
        while chunk:
            chunks.extend(chunk)
            if len(chunks) > limit:
                raise oversized
            chunk = await upload.read(CHUNK_SIZE)
        from app.services import image_service

        payload = image_service.normalise_profile_photo(bytes(chunks))
        mime, ext = image_service.WEBP_MIME, image_service.WEBP_EXT
    else:
        collected = bytearray()
        chunk = head
        while chunk:
            collected.extend(chunk)
            if len(collected) > limit:
                raise oversized
            chunk = await upload.read(CHUNK_SIZE)
        payload = bytes(collected)

    digest = hashlib.sha256(payload)
    size = len(payload)
    # Kept as an opaque, unique reference for compatibility; the bytes live in `blob`.
    relative = _relative_path(ext)

    asset = MediaAsset(
        owner_id=owner.id,
        purpose=purpose,
        storage_path=relative,
        content_type=mime,
        byte_size=size,
        checksum_sha256=digest.hexdigest(),
        original_filename=_safe_display_name(upload.filename),
        blob=payload,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    logger.info(
        "Stored media %s for user %s (%s, %d bytes)", asset.id, owner.id, mime, size
    )
    return asset


def read_bytes(asset: MediaAsset) -> bytes:
    """The file's bytes: from the database, or from disk for rows written before `blob`."""
    if asset.blob is not None:
        return bytes(asset.blob)
    path = absolute_path(asset)
    if not path.is_file():
        raise NotFoundError("This file is no longer available.")
    return path.read_bytes()


def absolute_path(asset: MediaAsset) -> Path:
    """Resolve a stored asset to an absolute path, refusing anything outside the root."""
    root = _media_root()
    path = (root / asset.storage_path).resolve()
    if root not in path.parents:
        raise NotFoundError("This file could not be found.")
    return path


def readable_by(asset: MediaAsset, user: User) -> bool:
    """Owners read their own uploads; administrators read everything for review."""
    return asset.owner_id == user.id or user.role is UserRole.ADMIN


def delete_asset(db: Session, asset: MediaAsset) -> None:
    """Remove the file and its row. Missing files are not an error."""
    try:
        absolute_path(asset).unlink(missing_ok=True)
    except (NotFoundError, OSError):
        logger.warning("Could not remove stored file for media %s", asset.id)
    db.delete(asset)
    db.commit()


def set_profile_photo(db: Session, user: User, asset: MediaAsset) -> None:
    """Point the member at a freshly uploaded picture, and remove the one it replaces.

    The old file is deleted immediately rather than left for the sweep: a replaced
    avatar is known-dead the moment the new one lands, and leaving faces on disk that
    nobody references is exactly the kind of thing a privacy review asks about.
    """
    previous_id = user.profile_photo_asset_id
    user.profile_photo_asset_id = asset.id
    # Uploading a picture supersedes any legacy external link.
    user.profile_photo_url = None
    db.commit()
    db.refresh(user)
    if previous_id and previous_id != asset.id:
        previous = db.get(MediaAsset, previous_id)
        if previous is not None:
            if is_reported(db, previous.id):
                # Evidence: the office still has to be able to look at what was
                # complained about, so the file stays and the sweep will keep it too.
                logger.info(
                    "Kept reported profile photo %s for user %s after replacement", previous_id, user.id
                )
            else:
                delete_asset(db, previous)
                logger.info("Replaced profile photo for user %s (removed %s)", user.id, previous_id)


def clear_profile_photo(db: Session, user: User) -> bool:
    """Remove the member's picture. Returns False when there was nothing to remove."""
    asset_id = user.profile_photo_asset_id
    if asset_id is None:
        return False
    user.profile_photo_asset_id = None
    db.commit()
    asset = db.get(MediaAsset, asset_id)
    if asset is not None and not is_reported(db, asset.id):
        delete_asset(db, asset)
    logger.info("Cleared profile photo for user %s", user.id)
    return True


def is_reported(db: Session, asset_id) -> bool:
    """True when a report names this asset — evidence, so the file is never deleted."""
    from app.models.report import Report

    return db.scalar(select(Report.id).where(Report.reported_photo_asset_id == asset_id)) is not None


def profile_photo_asset(db: Session, user: User) -> MediaAsset | None:
    """The member's uploaded picture, or None. Missing files are treated as absent."""
    if user.profile_photo_asset_id is None:
        return None
    asset = db.get(MediaAsset, user.profile_photo_asset_id)
    if asset is None or asset.purpose != PURPOSE_PROFILE_PHOTO:
        return None
    return asset


def asset_public_url(asset: MediaAsset) -> str:
    """API path the mobile app or dashboard can request with its access token."""
    return f"{settings.API_V1_PREFIX}/media/{asset.id}"


# --------------------------------------------------------------- housekeeping
@dataclasses.dataclass
class SweepResult:
    """What one orphan sweep did (or would do, with `dry_run`)."""

    deleted: int = 0
    bytes_reclaimed: int = 0
    kept_referenced: int = 0
    kept_too_new: int = 0
    dry_run: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return dataclasses.asdict(self)

    def __str__(self) -> str:  # pragma: no cover - CLI output
        verb = "would delete" if self.dry_run else "deleted"
        return (
            f"{verb} {self.deleted} orphaned file(s) ({self.bytes_reclaimed} bytes); "
            f"kept {self.kept_referenced} referenced, {self.kept_too_new} within retention"
        )


@dataclasses.dataclass
class StorageStats:
    files: int = 0
    bytes: int = 0
    orphans: int = 0
    orphan_bytes: int = 0
    oldest: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "files": self.files,
            "bytes": self.bytes,
            "orphans": self.orphans,
            "orphan_bytes": self.orphan_bytes,
            "oldest": self.oldest.isoformat() if self.oldest else None,
        }


def _is_orphan(asset: MediaAsset, reference_sets: tuple[set, set, set, set]) -> bool:
    verification_ids, vehicle_ids, profile_ids, reported_ids = reference_sets
    return (
        asset.id not in verification_ids
        and asset.id not in vehicle_ids
        and asset.id not in profile_ids
        and asset.id not in reported_ids
    )


def _reference_sets(db: Session) -> tuple[set, set, set, set]:
    """Every asset id that something still points at — never delete these."""
    verification_ids = {
        row for row in db.scalars(
            select(Verification.document_asset_id).where(Verification.document_asset_id.is_not(None))
        )
    }
    vehicle_ids: set = set()
    for photo, registration in db.execute(
        select(Vehicle.photo_asset_id, Vehicle.registration_asset_id)
    ):
        if photo:
            vehicle_ids.add(photo)
        if registration:
            vehicle_ids.add(registration)
    profile_ids = {
        row
        for row in db.scalars(
            select(User.profile_photo_asset_id).where(User.profile_photo_asset_id.is_not(None))
        )
    }
    # Phase 15: a picture named in a report is evidence — keep it even after the member
    # uploads a different photo or removes theirs.
    from app.models.report import Report

    reported_ids = {
        row
        for row in db.scalars(
            select(Report.reported_photo_asset_id).where(Report.reported_photo_asset_id.is_not(None))
        )
    }
    return verification_ids, vehicle_ids, profile_ids, reported_ids


def sweep_orphans(
    db: Session,
    *,
    older_than_days: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> SweepResult:
    """Delete uploads that no record references, once they are old enough.

    An upload becomes an orphan when a member picks a photo and never submits the
    form, or replaces one upload with another. The retention window is the safety
    margin: a file that is a few minutes old may simply be mid-flow, so nothing
    younger than `MEDIA_ORPHAN_RETENTION_DAYS` is touched.
    """
    days = older_than_days if older_than_days is not None else settings.MEDIA_ORPHAN_RETENTION_DAYS
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=days)
    result = SweepResult(dry_run=dry_run)
    references = _reference_sets(db)

    candidates = db.scalars(select(MediaAsset).order_by(MediaAsset.created_at)).all()
    for asset in candidates:
        created = asset.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if not _is_orphan(asset, references):
            result.kept_referenced += 1
            continue
        if created is not None and created > cutoff:
            result.kept_too_new += 1
            continue
        result.deleted += 1
        result.bytes_reclaimed += asset.byte_size
        if dry_run:
            continue
        try:
            absolute_path(asset).unlink(missing_ok=True)
        except (NotFoundError, OSError):  # pragma: no cover - defensive
            logger.warning("Could not remove orphaned file for media %s", asset.id)
        db.delete(asset)

    if not dry_run:
        db.commit()
    logger.info("Media sweep: %s", result)
    return result


def storage_stats(db: Session) -> StorageStats:
    """Counts for the runbook and `GET /admin/media`."""
    references = _reference_sets(db)
    stats = StorageStats()
    total_bytes = db.scalar(select(func.coalesce(func.sum(MediaAsset.byte_size), 0))) or 0
    stats.files = db.scalar(select(func.count(MediaAsset.id))) or 0
    stats.bytes = int(total_bytes)
    oldest = db.scalar(select(func.min(MediaAsset.created_at)))
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    stats.oldest = oldest
    for asset in db.scalars(select(MediaAsset)):
        if _is_orphan(asset, references):
            stats.orphans += 1
            stats.orphan_bytes += asset.byte_size
    return stats
