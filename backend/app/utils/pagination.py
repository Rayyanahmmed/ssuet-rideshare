"""Cursor pagination helpers for feeds (§19).

A cursor is `base64("<iso8601>|<uuid>")` of the last row's sort key, so a feed
stays stable even when new rides are published while the user scrolls.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

from app.core.exceptions import ValidationAppError


def encode_cursor(timestamp: datetime, row_id: uuid.UUID) -> str:
    raw = f"{timestamp.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        timestamp_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(timestamp_str), uuid.UUID(id_str)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ValidationAppError("The pagination cursor is invalid. Refresh the list.") from None
