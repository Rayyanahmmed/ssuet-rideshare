"""Notification history + Expo push device registration (§12).

Notifications are written by the business services (request accepted, trip
started, new chat message, …). This module is the member-facing surface: read
them, mark them read, and register/remove the device that should receive pushes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models.notification import DeviceToken, Notification
from app.schemas.common import MessageOut
from app.schemas.notification import (
    DeviceTokenIn,
    DeviceTokenOut,
    MarkAllReadOut,
    NotificationListOut,
    NotificationOut,
    UnreadCountOut,
)
from app.services import push_service
from app.utils.pagination import decode_cursor, encode_cursor

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _serialize(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        type=row.type,
        title=row.title,
        body=row.body,
        is_read=row.is_read,
        read_at=row.read_at,
        data=row.data,
        created_at=row.created_at,
    )


def _unread_count(db, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


@router.get("", response_model=NotificationListOut, summary="My notifications (newest first)")
def list_notifications(
    current_user: CurrentUser,
    db: DbSession,
    unread_only: bool = Query(default=False),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> NotificationListOut:
    query = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    if cursor:
        created_at, row_id = decode_cursor(cursor)
        query = query.where(
            (Notification.created_at < created_at)
            | ((Notification.created_at == created_at) & (Notification.id < row_id))
        )

    rows = list(
        db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return NotificationListOut(
        items=[_serialize(row) for row in rows],
        next_cursor=encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
        count=len(rows),
        unread_count=_unread_count(db, current_user.id),
    )


@router.get("/unread-count", response_model=UnreadCountOut, summary="Badge count")
def unread_count(current_user: CurrentUser, db: DbSession) -> UnreadCountOut:
    return UnreadCountOut(unread_count=_unread_count(db, current_user.id))


@router.post("/read-all", response_model=MarkAllReadOut, summary="Mark every notification as read")
def mark_all_read(current_user: CurrentUser, db: DbSession) -> MarkAllReadOut:
    rows = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == current_user.id, Notification.is_read.is_(False)
            )
        ).all()
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_read = True
        row.read_at = now
    if rows:
        db.commit()
    return MarkAllReadOut(marked_read=len(rows))


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark one as read")
def mark_read(notification_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> NotificationOut:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != current_user.id:
        raise NotFoundError("This notification could not be found.")
    if not row.is_read:
        from datetime import datetime, timezone

        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return _serialize(row)


# ------------------------------------------------------------------- devices
@router.get("/devices", response_model=list[DeviceTokenOut], summary="My registered devices")
def list_devices(current_user: CurrentUser, db: DbSession) -> list[DeviceTokenOut]:
    rows = list(
        db.scalars(select(DeviceToken).where(DeviceToken.user_id == current_user.id)).all()
    )
    return [
        DeviceTokenOut(
            id=row.id,
            token=row.token,
            platform=row.platform,
            is_active=row.is_active,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]


@router.post(
    "/devices",
    response_model=DeviceTokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register an Expo push token",
)
def register_device(
    payload: DeviceTokenIn, current_user: CurrentUser, db: DbSession
) -> DeviceTokenOut:
    device = push_service.register_device(db, current_user.id, payload.token, payload.platform)
    return DeviceTokenOut(
        id=device.id,
        token=device.token,
        platform=device.platform,
        is_active=device.is_active,
        last_seen_at=device.last_seen_at,
    )


@router.delete("/devices/{token}", response_model=MessageOut, summary="Unregister a device")
def remove_device(token: str, current_user: CurrentUser, db: DbSession) -> MessageOut:
    removed = push_service.deactivate_device(db, current_user.id, token)
    if not removed:
        raise NotFoundError("This device is not registered to your account.")
    return MessageOut(message="This device will no longer receive push notifications.")
