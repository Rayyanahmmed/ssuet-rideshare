"""In-process WebSocket room registry for trip chat (§11).

One room per conversation, keyed by *user*, so a member with the app open on two
devices gets the message on both — and presence is simply "does this user have at
least one socket in the room".

This is deliberately a single-process structure. Phase 8 documents the Redis
pub/sub upgrade path for a multi-worker deployment; the message envelope and the
REST endpoints stay identical either way.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("ssuet.rideshare.chat.hub")


class ChatHub:
    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, dict[uuid.UUID, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._lock = asyncio.Lock()

    async def connect(self, conversation_id: uuid.UUID, user_id: uuid.UUID, socket: WebSocket) -> None:
        async with self._lock:
            self._rooms[conversation_id][user_id].add(socket)

    async def disconnect(self, conversation_id: uuid.UUID, user_id: uuid.UUID, socket: WebSocket) -> None:
        async with self._lock:
            sockets = self._rooms.get(conversation_id, {}).get(user_id)
            if not sockets:
                return
            sockets.discard(socket)
            if not sockets:
                self._rooms[conversation_id].pop(user_id, None)
            if not self._rooms.get(conversation_id):
                self._rooms.pop(conversation_id, None)

    def online_ids(self, conversation_id: uuid.UUID) -> set[uuid.UUID]:
        return set(self._rooms.get(conversation_id, {}).keys())

    async def broadcast(
        self,
        conversation_id: uuid.UUID,
        payload: dict[str, Any],
        *,
        exclude_user: uuid.UUID | None = None,
        include_sender: bool = True,
    ) -> None:
        if not include_sender:
            await self.broadcast(conversation_id, payload, exclude_user=exclude_user)
            return
        targets = [
            (user_id, socket)
            for user_id, sockets in list(self._rooms.get(conversation_id, {}).items())
            if user_id != exclude_user
            for socket in list(sockets)
        ]
        for user_id, socket in targets:
            try:
                await socket.send_json(payload)
            except Exception:  # client vanished mid-send
                await self.disconnect(conversation_id, user_id, socket)

    async def send_to_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, payload: dict[str, Any]
    ) -> None:
        for socket in list(self._rooms.get(conversation_id, {}).get(user_id, set())):
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect(conversation_id, user_id, socket)


hub = ChatHub()
