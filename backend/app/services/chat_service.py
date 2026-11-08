"""Private trip chat (§11).

A conversation is created automatically when a driver accepts a request, so the
two members can coordinate the exact meeting point. Only those two people — and
an administrator — may read or write in it; the WebSocket layer enforces the same
rule independently (defence in depth).

Message notifications are persisted (and, in production, pushed) for the *other*
participant only, and never for a blocked pair.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.chat import Conversation, Message
from app.models.enums import UserRole
from app.models.trip import Trip
from app.models.user import User, UserBlock
from app.schemas.chat import (
    ChatParticipantOut,
    ConversationListOut,
    ConversationOut,
    MessageListOut,
    MessageOut,
)
from app.services.notification_service import create_notification_from_template
from app.utils.pagination import decode_cursor, encode_cursor

logger = logging.getLogger("ssuet.rideshare.chat")

PREVIEW_LENGTH = 120


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _blocked_between(db: Session, first: uuid.UUID, second: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(UserBlock.id).where(
                ((UserBlock.blocker_id == first) & (UserBlock.blocked_id == second))
                | ((UserBlock.blocker_id == second) & (UserBlock.blocked_id == first))
            )
        )
        is not None
    )


# ------------------------------------------------------------------- access
def get_conversation_or_404(db: Session, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("This conversation could not be found.")
    return conversation


def participants(conversation: Conversation) -> tuple[User, User]:
    trip = conversation.trip
    return trip.driver, trip.passenger


def assert_participant(db: Session, conversation: Conversation, user: User) -> None:
    trip = conversation.trip
    if user.role is UserRole.ADMIN:
        return
    if trip is None or not trip.involves(user.id):
        raise ForbiddenError("This conversation is private to the two members of the trip.")


def counterpart_of(conversation: Conversation, user: User) -> User:
    trip = conversation.trip
    return trip.passenger if trip.driver_id == user.id else trip.driver


# ------------------------------------------------------------------ reading
def _participant_out(user: User, online: set[uuid.UUID]) -> ChatParticipantOut:
    return ChatParticipantOut(
        id=user.id,
        full_name=user.full_name,
        profile_photo_url=user.photo_url,
        department=user.department,
        verification_status=user.verification_status,
        is_online=user.id in online,
    )


def _unread_count(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.read_at.is_(None),
            )
        )
        or 0
    )


def serialize_conversation(
    db: Session, conversation: Conversation, viewer: User, online: set[uuid.UUID] | None = None
) -> ConversationOut:
    trip = conversation.trip
    counterpart = counterpart_of(conversation, viewer)
    last_message = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return ConversationOut(
        id=conversation.id,
        trip_id=conversation.trip_id,
        trip_status=str(trip.status) if trip is not None else "UNKNOWN",
        direction=trip.ride.direction if trip is not None and trip.ride is not None else None,
        pickup_area=trip.ride.pickup_area if trip is not None and trip.ride is not None else None,
        destination_area=trip.ride.destination_area if trip is not None and trip.ride is not None else None,
        departure_at=_aware(trip.ride.departure_at) if trip is not None and trip.ride is not None else None,
        counterpart=_participant_out(counterpart, online or set()),
        last_message_at=_aware(conversation.last_message_at),
        last_message_preview=conversation.last_message_preview,
        last_message_is_mine=last_message is not None and last_message.sender_id == viewer.id,
        unread_count=_unread_count(db, conversation.id, viewer.id),
    )


def list_conversations(
    db: Session, viewer: User, online: set[uuid.UUID] | None = None
) -> ConversationListOut:
    conversations = list(
        db.scalars(
            select(Conversation)
            .join(Trip, Trip.id == Conversation.trip_id)
            .where((Trip.driver_id == viewer.id) | (Trip.passenger_id == viewer.id))
            .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
        ).all()
    )
    items = [serialize_conversation(db, row, viewer, online) for row in conversations]
    return ConversationListOut(
        items=items, count=len(items), unread_total=sum(item.unread_count for item in items)
    )


def list_messages(
    db: Session,
    conversation: Conversation,
    viewer: User,
    *,
    cursor: str | None = None,
    limit: int = 30,
) -> MessageListOut:
    """Newest-first page history. `next_cursor` walks further back in time."""
    query = select(Message).where(Message.conversation_id == conversation.id)
    if cursor:
        created_at, message_id = decode_cursor(cursor)
        query = query.where(
            (Message.created_at < created_at)
            | ((Message.created_at == created_at) & (Message.id < message_id))
        )
    rows = list(
        db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(_aware(rows[-1].created_at), rows[-1].id) if has_more and rows else None
    return MessageListOut(
        items=[serialize_message(row, viewer) for row in rows],
        next_cursor=next_cursor,
        count=len(rows),
    )


def serialize_message(message: Message, viewer: User) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        body=message.body,
        read_at=_aware(message.read_at),
        created_at=_aware(message.created_at),
        is_mine=message.sender_id == viewer.id,
    )


# ------------------------------------------------------------------ writing
def create_message(db: Session, conversation: Conversation, sender: User, body: str) -> Message:
    """Persist a message, refresh the conversation preview and notify the other side."""
    cleaned = body.strip()
    if not cleaned:
        raise ValidationAppError("Type a message before sending.")
    if len(cleaned) > 2000:
        raise ValidationAppError("Messages are limited to 2000 characters.")

    trip = conversation.trip
    if trip is None:  # pragma: no cover - FK guarantees a trip
        raise NotFoundError("This conversation could not be found.")
    if sender.id not in (trip.driver_id, trip.passenger_id):
        raise ForbiddenError("This conversation is private to the two members of the trip.")

    recipient = counterpart_of(conversation, sender)
    if _blocked_between(db, sender.id, recipient.id):
        raise ForbiddenError(
            "You cannot message this member because one of you has blocked the other.",
            details={"reason_code": "BLOCKED"},
        )
    if str(trip.status) in ("CANCELLED",):
        raise ConflictError("This trip was cancelled — the conversation is now read-only.")

    # Message order must be exact: two messages sent in the same microsecond
    # would otherwise fall back to a random UUID tiebreak. Nudging `created_at`
    # forward by 1µs keeps insertion order == display order, which also makes the
    # (created_at, id) cursor pagination stable.
    now = utcnow()
    previous = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if previous is not None:
        previous_at = _aware(previous.created_at)
        if previous_at is not None and previous_at >= now:
            now = previous_at + timedelta(microseconds=1)

    message = Message(
        conversation_id=conversation.id, sender_id=sender.id, body=cleaned, created_at=now
    )
    db.add(message)
    conversation.last_message_at = now
    conversation.last_message_preview = cleaned[:PREVIEW_LENGTH]

    create_notification_from_template(
        db,
        user_id=recipient.id,
        template="NEW_MESSAGE",
        commit=False,
        sender_name=sender.full_name,
        preview=cleaned[:60],
        data={
            "screen": "chat",
            "conversation_id": str(conversation.id),
            "trip_id": str(conversation.trip_id),
        },
    )
    db.commit()
    db.refresh(message)
    db.refresh(conversation)
    return message


def mark_read(db: Session, conversation: Conversation, viewer: User) -> tuple[int, datetime]:
    """Mark every incoming message as read; returns how many were affected."""
    now = utcnow()
    rows = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.sender_id != viewer.id,
                Message.read_at.is_(None),
            )
        ).all()
    )
    for row in rows:
        row.read_at = now
    if rows:
        db.commit()
    return len(rows), now


def conversation_for_trip(db: Session, trip_id: uuid.UUID) -> Conversation | None:
    return db.scalar(select(Conversation).where(Conversation.trip_id == trip_id))
