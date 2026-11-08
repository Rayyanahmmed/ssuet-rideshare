"""Trip chat — REST fallback plus the WebSocket (§11).

`GET/POST /chat/conversations/...` are always available and are what the mobile
app falls back to when a socket cannot be established (bad network, proxy that
blocks upgrades). The socket adds live delivery, typing indicators, presence and
read receipts on top of the same service functions, so there is exactly one code
path that writes a message.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.enums import AccountStatus
from app.models.trip import Trip
from app.models.user import User
from app.schemas.chat import (
    ConversationListOut,
    ConversationOut,
    MessageCreateIn,
    MessageListOut,
    MessageOut,
    ReadReceiptOut,
)
from app.services import chat_service
from app.services.chat_hub import hub

logger = logging.getLogger("ssuet.rideshare.chat")

router = APIRouter(prefix="/chat", tags=["Chat"])

WS_UNAUTHORIZED = 1008  # policy violation: close code the client treats as "re-authenticate"


# ---------------------------------------------------------------- REST surface
@router.get("/conversations", response_model=ConversationListOut, summary="My conversations")
def list_conversations(current_user: CurrentUser, db: DbSession) -> ConversationListOut:
    return chat_service.list_conversations(db, current_user)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    summary="One conversation (participants only)",
)
def get_conversation(
    conversation_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> ConversationOut:
    conversation = chat_service.get_conversation_or_404(db, conversation_id)
    chat_service.assert_participant(db, conversation, current_user)
    return chat_service.serialize_conversation(
        db, conversation, current_user, hub.online_ids(conversation.id)
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListOut,
    summary="Message history (newest first, cursor walks backwards)",
)
def list_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> MessageListOut:
    conversation = chat_service.get_conversation_or_404(db, conversation_id)
    chat_service.assert_participant(db, conversation, current_user)
    return chat_service.list_messages(db, conversation, current_user, cursor=cursor, limit=limit)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message (REST fallback when the socket is unavailable)",
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreateIn,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageOut:
    conversation = chat_service.get_conversation_or_404(db, conversation_id)
    chat_service.assert_participant(db, conversation, current_user)
    message = chat_service.create_message(db, conversation, current_user, payload.body)
    outgoing = chat_service.serialize_message(message, current_user).model_dump(mode="json")
    # A member sending over the REST fallback still sees the message arrive live
    # on any socket they have open.
    await _deliver_message(conversation_id, outgoing, current_user.id)
    return chat_service.serialize_message(message, current_user)


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=ReadReceiptOut,
    summary="Mark every incoming message as read",
)
async def mark_read(
    conversation_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> ReadReceiptOut:
    conversation = chat_service.get_conversation_or_404(db, conversation_id)
    chat_service.assert_participant(db, conversation, current_user)
    count, read_at = chat_service.mark_read(db, conversation, current_user)
    if count:
        await hub.broadcast(
            conversation_id,
            {
                "type": "read",
                "user_id": str(current_user.id),
                "read_at": read_at.isoformat(),
                "messages_marked_read": count,
            },
            exclude_user=current_user.id,
        )
    return ReadReceiptOut(
        conversation_id=conversation_id, messages_marked_read=count, read_at=read_at
    )


# ------------------------------------------------------------------- WebSocket
def _extract_token(socket: WebSocket, query_token: str | None) -> str:
    if query_token:
        return query_token
    header = socket.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    raise UnauthorizedError("A token is required to open the chat socket.")


def _load_socket_user(token: str) -> User:
    """Authenticate the handshake exactly like the REST dependency does."""
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload.get("sub")))
    except (JWTError, TypeError, ValueError):
        raise UnauthorizedError("Your session has expired. Please log in again.") from None

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise UnauthorizedError("This account no longer exists.")
        if user.account_status is not AccountStatus.ACTIVE:
            raise ForbiddenError("This account cannot open chat.")
        db.expunge(user)
        return user


def _load_room(conversation_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
    """Validate room access in a fresh session and return the handshake payload."""
    with SessionLocal() as db:
        conversation = db.get(chat_service.Conversation, conversation_id)
        if conversation is None:
            return None
        trip = db.get(Trip, conversation.trip_id)
        if trip is None:
            return None
        allowed = trip.driver_id == user_id or trip.passenger_id == user_id
        if not allowed:
            return None
        counterpart_id = trip.passenger_id if trip.driver_id == user_id else trip.driver_id
        counterpart = db.get(User, counterpart_id)
        return {
            "conversation_id": str(conversation.id),
            "trip_id": str(conversation.trip_id),
            "trip_status": str(trip.status),
            "participants": [
                {"id": str(trip.driver_id), "role": "DRIVER"},
                {"id": str(trip.passenger_id), "role": "PASSENGER"},
            ],
            "counterpart": {
                "id": str(counterpart.id) if counterpart else None,
                "full_name": counterpart.full_name if counterpart else "Your trip partner",
            },
            "last_message_at": (
                chat_service._aware(conversation.last_message_at).isoformat()
                if conversation.last_message_at
                else None
            ),
        }


async def _deliver_message(
    conversation_id: uuid.UUID, message_payload: dict[str, Any], sender_id: uuid.UUID
) -> None:
    """Fan a new message out with `is_mine` computed for *each* recipient.

    `is_mine` is viewer-specific, so broadcasting one shared payload would tell
    the other member their own message was theirs. The socket payload is
    identical in shape to the REST one — only this flag differs.
    """
    for user_id in hub.online_ids(conversation_id):
        payload = {
            "type": "message",
            "message": {**message_payload, "is_mine": user_id == sender_id},
        }
        await hub.send_to_user(conversation_id, user_id, payload)


async def _handle_message(
    socket: WebSocket, conversation_id: uuid.UUID, user_id: uuid.UUID, body: str
) -> None:
    def _persist() -> dict[str, Any] | None:
        with SessionLocal() as db:
            conversation = db.get(chat_service.Conversation, conversation_id)
            user = db.get(User, user_id)
            if conversation is None or user is None:
                return None
            message = chat_service.create_message(db, conversation, user, body)
            payload = chat_service.serialize_message(message, user).model_dump(mode="json")
            # The socket owns its own session, so it flushes the push itself.
            from app.services import push_service

            push_service.flush_pending(db)
            return payload

    try:
        payload = await run_in_threadpool(_persist)
    except AppError as exc:
        await socket.send_json({"type": "error", "code": exc.code, "message": exc.message})
        return

    if payload is None:
        await socket.send_json(
            {"type": "error", "code": "NOT_FOUND", "message": "This conversation no longer exists."}
        )
        return

    await _deliver_message(conversation_id, payload, user_id)


@router.websocket("/ws/{conversation_id}")
async def chat_socket(
    socket: WebSocket,
    conversation_id: uuid.UUID,
    token: str | None = Query(default=None, description="Access token (or send an Authorization header)"),
) -> None:
    """Live chat. Frames are documented in `app/schemas/chat.py`."""
    try:
        raw_token = _extract_token(socket, token)
        user = await run_in_threadpool(_load_socket_user, raw_token)
    except AppError as exc:
        await socket.close(code=WS_UNAUTHORIZED, reason=exc.message[:120])
        return

    room = await run_in_threadpool(_load_room, conversation_id, user.id)
    if room is None:
        await socket.close(code=WS_UNAUTHORIZED, reason="You are not part of this conversation.")
        return

    await socket.accept()
    await hub.connect(conversation_id, user.id, socket)
    await socket.send_json(
        {
            "type": "ready",
            "user_id": str(user.id),
            "online": [str(uid) for uid in hub.online_ids(conversation_id)],
            **room,
        }
    )
    await hub.broadcast(
        conversation_id,
        {"type": "presence", "online": [str(uid) for uid in hub.online_ids(conversation_id)]},
        exclude_user=user.id,
    )

    try:
        while True:
            frame = await socket.receive_json()
            frame_type = frame.get("type")

            if frame_type == "ping":
                await socket.send_json({"type": "pong"})
            elif frame_type == "message":
                body = str(frame.get("body") or "")
                await _handle_message(socket, conversation_id, user.id, body)
            elif frame_type == "typing":
                await hub.broadcast(
                    conversation_id,
                    {
                        "type": "typing",
                        "user_id": str(user.id),
                        "is_typing": bool(frame.get("is_typing", True)),
                    },
                    exclude_user=user.id,
                )
            elif frame_type == "read":

                def _mark() -> dict[str, Any]:
                    with SessionLocal() as db:
                        conversation = db.get(chat_service.Conversation, conversation_id)
                        viewer = db.get(User, user.id)
                        if conversation is None or viewer is None:
                            return {"type": "error", "code": "NOT_FOUND", "message": "Conversation missing."}
                        count, read_at = chat_service.mark_read(db, conversation, viewer)
                        return {
                            "type": "read",
                            "user_id": str(user.id),
                            "read_at": read_at.isoformat(),
                            "messages_marked_read": count,
                        }

                receipt = await run_in_threadpool(_mark)
                if receipt.get("type") == "read":
                    await hub.broadcast(conversation_id, receipt, exclude_user=user.id)
                else:
                    await socket.send_json(receipt)
            else:
                await socket.send_json(
                    {
                        "type": "error",
                        "code": "VALIDATION_ERROR",
                        "message": f"Unknown frame type: {frame_type!r}",
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        logger.exception("Chat socket error for conversation %s", conversation_id)
    finally:
        await hub.disconnect(conversation_id, user.id, socket)
        await hub.broadcast(
            conversation_id,
            {"type": "presence", "online": [str(uid) for uid in hub.online_ids(conversation_id)]},
        )
