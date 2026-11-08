"""User profile & verification endpoints — `/api/v1/users` (§5, §15)."""

from __future__ import annotations

import io
import uuid
from typing import Literal

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.rate_limit import limiter
from app.models.media import PURPOSE_PROFILE_PHOTO
from app.models.review import Review
from app.models.user import User, UserBlock
from app.schemas.common import MessageOut
from app.schemas.report import PhotoReportIn, ReportOut
from app.schemas.user import (
    ReviewOut,
    UserMeOut,
    UserPublicOut,
    UserUpdateIn,
    VerificationOut,
    VerificationSubmitIn,
)
from app.services import auth_service, media_service, report_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserMeOut, summary="My profile")
def read_me(current_user: CurrentUser) -> UserMeOut:
    return UserMeOut.model_validate(current_user)


@router.patch("/me", response_model=UserMeOut, summary="Update my profile")
def update_me(payload: UserUpdateIn, current_user: CurrentUser, db: DbSession) -> UserMeOut:
    data = payload.model_dump(exclude_unset=True)

    if "phone" in data and data["phone"] != current_user.phone:
        if db.scalar(select(User.id).where(User.phone == data["phone"])) is not None:
            raise ValidationAppError("This phone number is already in use.", details={"phone": "taken"})

    # flat fields on the user row
    for field in ("full_name", "department", "phone"):
        if field in data:
            setattr(current_user, field, data.pop(field))
    if "profile_photo_url" in data:
        current_user.profile_photo_url = str(data.pop("profile_photo_url"))

    # role-specific fields
    if current_user.student_profile is not None:
        profile = current_user.student_profile
        for field in ("home_area", "degree_programme", "semester", "batch_year"):
            if field in data:
                setattr(profile, field, data.pop(field))
    if current_user.teacher_profile is not None:
        profile = current_user.teacher_profile
        for field in ("home_area", "designation"):
            if field in data:
                setattr(profile, field, data.pop(field))

    db.commit()
    db.refresh(current_user)
    return UserMeOut.model_validate(current_user)


@router.get(
    "/{user_id}/public",
    response_model=UserPublicOut,
    summary="Public profile of another member",
    description="Never includes email, phone number, university ID or home area (§8, §15).",
)
def read_public_profile(user_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> UserPublicOut:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("This member could not be found.")
    return UserPublicOut.model_validate(user)


@router.get(
    "/{user_id}/reviews",
    response_model=list[ReviewOut],
    summary="Reviews received by a member (legacy alias)",
    deprecated=True,
    description=(
        "Kept for Phase 2 clients. The canonical, paginated endpoint with the rating "
        "distribution is `GET /api/v1/reviews/users/{user_id}` (§3.10)."
    ),
)
def read_reviews(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> list[ReviewOut]:
    if db.get(User, user_id) is None:
        raise NotFoundError("This member could not be found.")
    rows = db.scalars(
        select(Review)
        .where(Review.subject_id == user_id, Review.is_hidden.is_(False))
        .order_by(Review.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        ReviewOut(
            id=r.id,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
            author=UserPublicOut.model_validate(r.author),
        )
        for r in rows
    ]


# --------------------------------------------------------------- profile photo
@router.post(
    "/me/photo",
    response_model=UserMeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload my profile photo",
    description=(
        "Multipart upload of a JPG, PNG or WebP picture up to `MAX_PROFILE_PHOTO_BYTES` "
        "(2 MB). Types are checked by magic number, not by extension or the declared "
        "content type. The picture is then normalised before it is stored: metadata "
        "(including GPS) is stripped, the EXIF orientation is applied, it is centre-"
        "cropped square and resized to `PROFILE_PHOTO_MAX_DIMENSION` (512 px) and "
        "re-encoded as WebP — so `byte_size` in the response is the stored size, not "
        "the uploaded one. Replacing a photo deletes the previous file immediately. Any "
        "member can then read it at `GET /users/{user_id}/photo`."
    ),
)
@limiter.limit("10/minute")
async def upload_profile_photo(
    request: Request,  # required by the rate limiter
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="JPG, PNG or WebP up to 2 MB"),
) -> UserMeOut:
    asset = await media_service.store_upload(
        db,
        current_user,
        file,
        purpose=PURPOSE_PROFILE_PHOTO,
        max_bytes=settings.MAX_PROFILE_PHOTO_BYTES,
        images_only=True,
        normalise=True,
    )
    media_service.set_profile_photo(db, current_user, asset)
    return UserMeOut.model_validate(current_user)


@router.post(
    "/{user_id}/photo/report",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Report a member's profile photo",
    description=(
        "Files a complaint about a picture, with a reason and a short description. The "
        "exact uploaded file is pinned on the report, so the office can still see what "
        "was complained about even if the member uploads a different photo meanwhile. "
        "One open photo report per member at a time; the reporter is told the outcome."
    ),
)
@limiter.limit("5/minute")
def report_profile_photo(
    user_id: uuid.UUID,
    payload: PhotoReportIn,
    request: Request,  # required by the rate limiter
    current_user: CurrentUser,
    db: DbSession,
) -> ReportOut:
    return report_service.create_photo_report(db, current_user, user_id, payload)


@router.delete(
    "/me/photo",
    response_model=UserMeOut,
    summary="Remove my profile photo",
    description="Deletes the stored file and falls back to the legacy external link, if any.",
)
def delete_profile_photo(current_user: CurrentUser, db: DbSession) -> UserMeOut:
    media_service.clear_profile_photo(db, current_user)
    return UserMeOut.model_validate(current_user)


@router.get(
    "/{user_id}/photo",
    summary="Read a member's profile photo",
    description=(
        "Streams the stored picture. Readable by any signed-in member — a profile photo "
        "is part of how the community recognises each other, unlike an ID card.\n\n"
        "`size=thumb` returns a `PROFILE_PHOTO_THUMB_DIMENSION` (128 px) version derived "
        "on demand and cached in-process; use it for lists and cards. The URL includes "
        "the asset id as a cache key, so the response may be cached for an hour."
    ),
    response_class=StreamingResponse,
    responses={200: {"content": {"image/webp": {}}}, 404: {"description": "No photo set"}},
)
def read_profile_photo(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    size: Literal["full", "thumb"] = Query(default="full", description="full (512 px) or thumb (128 px)"),
) -> StreamingResponse:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("This member could not be found.")
    asset = media_service.profile_photo_asset(db, user)
    if asset is None:
        raise NotFoundError("This member has not set a profile photo.")
    original = media_service.read_bytes(asset)

    if size == "thumb":
        from app.services import image_service

        payload = image_service.cached_thumbnail(asset.checksum_sha256, original)
        # The ETag names the variant, so a client that first cached the full picture
        # does not get a 304 for a thumbnail it never downloaded.
        etag = f'"thumb-{asset.checksum_sha256[:26]}"'
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="image/webp",
            headers={
                "Content-Disposition": "inline",
                "Content-Length": str(len(payload)),
                "Cache-Control": "private, max-age=3600",
                "ETag": etag,
                "X-Content-Type-Options": "nosniff",
            },
        )

    return StreamingResponse(
        io.BytesIO(original),
        media_type=asset.content_type,
        headers={
            "Content-Disposition": "inline",
            "Content-Length": str(asset.byte_size),
            # Faces are semi-public inside the community, not on the open web.
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{asset.checksum_sha256[:32]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.post(
    "/me/verification",
    response_model=VerificationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit university ID for manual verification",
    description=(
        "For members whose email domain could not be verified automatically. An "
        "administrator approves or rejects the request; the account status moves to "
        "PENDING immediately."
    ),
)
def submit_verification(
    payload: VerificationSubmitIn, current_user: CurrentUser, db: DbSession
) -> VerificationOut:
    record = auth_service.submit_verification(db, current_user, payload)
    return VerificationOut.model_validate(record)


@router.get("/me/verifications", response_model=list[VerificationOut], summary="My verification history")
def my_verifications(current_user: CurrentUser, db: DbSession) -> list[VerificationOut]:
    return [
        VerificationOut.model_validate(v)
        for v in auth_service.verification_history(db, current_user.id)
    ]


@router.post("/{user_id}/block", response_model=MessageOut, summary="Block a member")
def block_user(user_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MessageOut:
    if user_id == current_user.id:
        raise ValidationAppError("You cannot block yourself.")
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("This member could not be found.")
    try:
        db.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("You have already blocked this member.") from None
    return MessageOut(message="Member blocked. You will not be matched with them again.")


@router.delete("/{user_id}/block", response_model=MessageOut, summary="Unblock a member")
def unblock_user(user_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MessageOut:
    block = db.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == user_id
        )
    )
    if block is None:
        raise NotFoundError("This member is not blocked.")
    db.delete(block)
    db.commit()
    return MessageOut(message="Member unblocked.")


@router.get("/me/blocks", response_model=list[UserPublicOut], summary="Members I have blocked")
def list_blocks(current_user: CurrentUser, db: DbSession) -> list[UserPublicOut]:
    rows = db.scalars(
        select(User)
        .join(UserBlock, UserBlock.blocked_id == User.id)
        .where(UserBlock.blocker_id == current_user.id)
    ).all()
    return [UserPublicOut.model_validate(u) for u in rows]
