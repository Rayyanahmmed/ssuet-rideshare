"""Expo push delivery (§12).

Design notes
------------
* Push must never make a business action fail: every network problem is logged
  and swallowed, and no user-facing endpoint waits on a successful send.
* Delivery is **post-commit**. Services create notifications inside their own
  transaction (often with `commit=False`), so pushing at creation time could
  announce a message that the database later rolled back. Instead each
  notification is queued on the SQLAlchemy session (`db.info["pending_push"]`)
  and the `after_commit` hook flushes the queue — exactly once, only for data
  that really exists.
* Expo answers with per-message *tickets*. A revoked app install answers
  `DeviceNotRegistered`, and that token is deactivated so we stop paying for it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import DeviceToken, Notification

logger = logging.getLogger("ssuet.rideshare.push")

#: Expo accepts at most 100 messages per request.
BATCH_SIZE = 100
_PENDING_KEY = "pending_push"


@dataclass
class PushDispatch:
    """Outcome of one flush — returned so tests (and logs) can assert on it."""

    attempted: int = 0
    tickets: list[dict[str, Any]] = field(default_factory=list)
    deactivated_tokens: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def sent(self) -> int:
        return len(self.tickets)


def queue_push(db: Session, notification: Notification) -> None:
    """Defer a push until the surrounding transaction commits."""
    db.info.setdefault(_PENDING_KEY, []).append(notification)


def flush_pending(db: Session) -> PushDispatch:
    """Send the pushes queued on this session — call **after** the business commit.

    The API dependency does this automatically for every REST request, and the
    chat socket does it after persisting a message. Notifications whose rows did
    not survive (rolled back) are dropped instead of being announced.
    """
    queued = db.info.pop(_PENDING_KEY, [])
    if not queued:
        return PushDispatch()

    live: list[Notification] = []
    for notification in queued:
        try:
            row = db.get(Notification, notification.id) if notification.id else None
        except Exception:  # pragma: no cover - defensive
            row = None
        if row is None and getattr(notification, "id", None) is None:
            # Never persisted at all (rolled back) — nothing to announce.
            row = db.scalar(
                select(Notification).where(
                    Notification.user_id == notification.user_id,
                    Notification.title == notification.title,
                    Notification.created_at == notification.created_at,
                )
            )
        if row is not None:
            live.append(row)
    return dispatch(db, live)


def _active_tokens(db: Session, user_id: uuid.UUID) -> list[DeviceToken]:
    return list(
        db.scalars(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True)
            )
        ).all()
    )


def build_messages(db: Session, notifications: list[Notification]) -> list[dict[str, Any]]:
    """Turn notifications into Expo message payloads (no network)."""
    payloads: list[dict[str, Any]] = []
    for notification in notifications:
        if notification.push_sent_at is not None:
            continue
        for device in _active_tokens(db, notification.user_id):
            payloads.append(
                {
                    "to": device.token,
                    "title": notification.title,
                    "body": notification.body,
                    "sound": "default",
                    "priority": "high",
                    "data": {
                        "notification_id": str(notification.id),
                        "type": str(notification.type),
                        **(notification.data or {}),
                    },
                }
            )
    return payloads


def _send_batches(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """POST to Expo in chunks. Split out so tests can stub the network."""
    tickets: list[dict[str, Any]] = []
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = settings.EXPO_ACCESS_TOKEN.strip()
    if token:
        # Required only for Expo projects with enhanced push security enabled.
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=5.0) as client:
        for start in range(0, len(payloads), BATCH_SIZE):
            batch = payloads[start : start + BATCH_SIZE]
            response = client.post(settings.EXPO_PUSH_URL, json=batch, headers=headers)
            response.raise_for_status()
            body = response.json()
            data = body.get("data")
            if isinstance(data, list):
                tickets.extend(data)
            elif isinstance(data, dict):
                tickets.append(data)
    return tickets


def _deactivate(db: Session, tokens: set[str]) -> list[str]:
    if not tokens:
        return []
    rows = list(db.scalars(select(DeviceToken).where(DeviceToken.token.in_(tokens))).all())
    for row in rows:
        row.is_active = False
    return [row.token for row in rows]


def dispatch(db: Session, notifications: list[Notification]) -> PushDispatch:
    """Send queued notifications to Expo and record the outcome. Never raises."""
    result = PushDispatch()
    if not notifications:
        return result
    if not settings.EXPO_PUSH_ENABLED or settings.ENVIRONMENT == "test":
        # Tests and disabled environments still persist notifications (§12).
        return result

    payloads = build_messages(db, notifications)
    result.attempted = len(payloads)
    if not payloads:
        for notification in notifications:
            notification.push_sent_at = _utcnow()
        db.commit()
        return result

    try:
        tickets = _send_batches(payloads)
    except Exception as exc:  # network, DNS, 5xx — never break the caller
        logger.warning("Expo push delivery failed: %s", exc)
        result.errors.append(str(exc))
        return result

    result.tickets = tickets
    dead: set[str] = set()
    for index, ticket in enumerate(tickets):
        if ticket.get("status") != "error":
            continue
        details = ticket.get("details") or {}
        if details.get("error") == "DeviceNotRegistered" and index < len(payloads):
            dead.add(str(payloads[index]["to"]))
        else:
            result.errors.append(str(ticket.get("message", "unknown push error")))

    result.deactivated_tokens = _deactivate(db, dead)
    now = _utcnow()
    for notification in notifications:
        notification.push_sent_at = now
    db.commit()
    logger.info(
        "Push dispatched: %s messages, %s tickets, %s tokens deactivated",
        result.attempted,
        len(tickets),
        len(result.deactivated_tokens),
    )
    return result


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def register_device(db: Session, user_id: uuid.UUID, token: str, platform: str) -> DeviceToken:
    """Register (or revive) an Expo push token for a device."""
    token = token.strip()
    existing = db.scalar(select(DeviceToken).where(DeviceToken.token == token))
    now = _utcnow()
    if existing is None:
        device = DeviceToken(user_id=user_id, token=token, platform=platform, is_active=True, last_seen_at=now)
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    # The same handset may have been used by a previous account: re-point it.
    existing.user_id = user_id
    existing.platform = platform
    existing.is_active = True
    existing.last_seen_at = now
    db.commit()
    db.refresh(existing)
    return existing


def deactivate_device(db: Session, user_id: uuid.UUID, token: str) -> bool:
    device = db.scalar(
        select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user_id)
    )
    if device is None or not device.is_active:
        return False
    device.is_active = False
    db.commit()
    return True
