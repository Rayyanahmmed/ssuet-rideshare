"""Media upload & retrieval — `/api/v1/uploads`, `/api/v1/media` (§4, §16, Phase 9).

Two things live here:

* `POST /uploads/verification` — multipart upload of a student/employee ID card or a
  fee receipt. Size, type and magic numbers are validated; the file is stored under
  `MEDIA_ROOT` and referenced by a UUID, never by a client-supplied path.
* `GET /media/{asset_id}` — streams the file back to its owner or to an
  administrator. Deliberately *not* a public static mount: an ID card is personal
  data, so every read is authorised.
"""

from __future__ import annotations

import io

import uuid

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.models.enums import UserRole
from app.models.media import PURPOSE_VERIFICATION_DOCUMENT, PURPOSE_VEHICLE_DOCUMENT, MediaAsset
from app.schemas.media import MediaAssetOut
from app.services import media_service
from app.core.exceptions import ForbiddenError, NotFoundError

router = APIRouter(tags=["media"])


@router.post(
    "/uploads/verification",
    response_model=MediaAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a verification document",
    description=(
        "Accepts a JPG, PNG, WebP or PDF file up to `MAX_UPLOAD_BYTES` (5 MB by "
        "default). The response id is passed to `POST /users/me/verification` as "
        "`document_asset_id`. Files are validated by content, not by extension, and "
        "are readable only by their owner and by administrators."
    ),
)
@limiter.limit("10/minute")
async def upload_verification_document(
    request: Request,  # required by the rate limiter
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="JPG, PNG, WebP or PDF up to 5 MB"),
) -> MediaAssetOut:
    asset = await media_service.store_upload(db, current_user, file)
    return MediaAssetOut.from_asset(asset)


@router.post(
    "/uploads/vehicle",
    response_model=MediaAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a vehicle photo or registration document",
    description=(
        "Same validation as the verification upload (JPG/PNG/WebP/PDF by content, "
        "`MAX_UPLOAD_BYTES`, 5 MB default). Pass the returned id to `POST /vehicles` as "
        "`photo_asset_id` or `registration_asset_id`."
    ),
)
@limiter.limit("10/minute")
async def upload_vehicle_document(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="Photo of the vehicle or its registration book"),
) -> MediaAssetOut:
    asset = await media_service.store_upload(
        db, current_user, file, purpose=PURPOSE_VEHICLE_DOCUMENT
    )
    return MediaAssetOut.from_asset(asset)


@router.get(
    "/media/{asset_id}",
    summary="Read an uploaded file",
    description=(
        "Streams the stored file. Allowed for the member who uploaded it and for "
        "administrators reviewing a verification request."
    ),
    responses={200: {"content": {"image/*": {}, "application/pdf": {}}}},
)
def read_media(asset_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> StreamingResponse:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise NotFoundError("This file could not be found.")
    if not media_service.readable_by(asset, current_user):
        raise ForbiddenError("You are not allowed to view this file.")
    data = media_service.read_bytes(asset)

    filename = asset.original_filename or f"{asset.id}.bin"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=asset.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(asset.byte_size),
            # Personal data: no shared caches, and never let a browser re-interpret it.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/media/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded file",
    description="The owner may withdraw an upload; administrators may remove any file.",
)
def delete_media(asset_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise NotFoundError("This file could not be found.")
    if asset.owner_id != current_user.id and current_user.role is not UserRole.ADMIN:
        raise ForbiddenError("You are not allowed to delete this file.")
    media_service.delete_asset(db, asset)
