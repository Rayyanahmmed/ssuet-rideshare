"""Chat contracts (§11) — REST fallback plus the WebSocket envelope.

The socket protocol is intentionally tiny and documented here so the mobile
client and any future dashboard viewer speak the same language:

    client → server   {"type": "message",  "body": "..."}
                      {"type": "typing",   "is_typing": true}
                      {"type": "read"}
                      {"type": "ping"}

    server → client   {"type": "ready",    "conversation_id": "...", "participants": [...]}
                      {"type": "message",  "message": MessageOut}
                      {"type": "typing",   "user_id": "...", "is_typing": true}
                      {"type": "read",     "user_id": "...", "read_at": "..."}
                      {"type": "presence", "online": ["user-id", ...]}
                      {"type": "error",    "code": "...", "message": "..."}
                      {"type": "pong"}
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import RideDirection, VerificationStatus


class MessageCreateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Type a message before sending.")
        return cleaned


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    read_at: datetime | None = None
    created_at: datetime
    is_mine: bool = False


class MessageListOut(BaseModel):
    """Newest first. `next_cursor` walks **backwards** through history."""

    items: list[MessageOut]
    next_cursor: str | None = None
    count: int


class ChatParticipantOut(BaseModel):
    id: uuid.UUID
    full_name: str
    profile_photo_url: str | None = None
    department: str
    verification_status: VerificationStatus
    is_online: bool = False


class ConversationOut(BaseModel):
    """One row in the chat list, with the trip context that justifies it."""

    id: uuid.UUID
    trip_id: uuid.UUID
    trip_status: str
    direction: RideDirection | None = None
    pickup_area: str | None = None
    destination_area: str | None = None
    departure_at: datetime | None = None

    counterpart: ChatParticipantOut
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    last_message_is_mine: bool = False
    unread_count: int = 0


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    count: int
    unread_total: int = 0


class ReadReceiptOut(BaseModel):
    conversation_id: uuid.UUID
    messages_marked_read: int
    read_at: datetime
