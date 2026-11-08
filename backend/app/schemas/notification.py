"""Notification + device contracts (§12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import NotificationType


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    is_read: bool
    read_at: datetime | None = None
    data: dict[str, Any] | None = None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None = None
    count: int
    unread_count: int


class UnreadCountOut(BaseModel):
    unread_count: int


class MarkAllReadOut(BaseModel):
    marked_read: int


class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=255)
    platform: Literal["android", "ios"] = "android"

    @field_validator("token")
    @classmethod
    def _looks_like_expo_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A device token is required.")
        return cleaned


class DeviceTokenOut(BaseModel):
    id: uuid.UUID
    token: str
    platform: str
    is_active: bool
    last_seen_at: datetime | None = None
