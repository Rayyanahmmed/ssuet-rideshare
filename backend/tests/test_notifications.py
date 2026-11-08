"""Phase 5 — notification + Expo push tests (§12)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.enums import NotificationType
from app.models.notification import DeviceToken, Notification
from app.services import push_service
from tests.helpers import passenger_setup, register

NOTIFICATIONS = "/api/v1/notifications"


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client, *, depart_in_minutes: int = 300):
    driver, vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=depart_in_minutes)}
    )
    passenger = register(client)
    created = client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    assert created.status_code == 201, created.text
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"])
    assert trip.status_code == 200, trip.text
    return driver, passenger, ride, trip.json()


# ------------------------------------------------------------------ inbox API
def test_accepting_a_request_notifies_both_sides(client):
    driver, passenger, _ride, _trip = matched_trip(client)

    for player in (driver, passenger):
        listing = client.get(NOTIFICATIONS, headers=player["headers"]).json()
        assert listing["count"] >= 1
        assert any(item["type"] == "RIDE_REQUEST_ACCEPTED" for item in listing["items"])
        assert listing["unread_count"] == listing["count"]


def test_notifications_are_private(client):
    driver, _passenger, _ride, _trip = matched_trip(client)
    outsider = register(client)

    driver_listing = client.get(NOTIFICATIONS, headers=driver["headers"]).json()
    outsider_listing = client.get(NOTIFICATIONS, headers=outsider["headers"]).json()
    driver_ids = {item["id"] for item in driver_listing["items"]}
    outsider_ids = {item["id"] for item in outsider_listing["items"]}
    assert driver_ids and driver_ids.isdisjoint(outsider_ids)

    stolen_id = driver_listing["items"][0]["id"]
    assert (
        client.post(f"{NOTIFICATIONS}/{stolen_id}/read", headers=outsider["headers"]).status_code
        == 404
    )
    assert client.get(f"{NOTIFICATIONS}/unread-count").status_code == 401


def test_unread_count_matches_the_list(client):
    driver, _passenger, _ride, _trip = matched_trip(client)
    listing = client.get(NOTIFICATIONS, headers=driver["headers"]).json()
    count = client.get(f"{NOTIFICATIONS}/unread-count", headers=driver["headers"]).json()
    assert count["unread_count"] == listing["unread_count"] >= 1


def test_mark_one_read_then_all(client):
    driver, _passenger, _ride, _trip = matched_trip(client)
    listing = client.get(NOTIFICATIONS, headers=driver["headers"]).json()
    first_id = listing["items"][0]["id"]

    marked = client.post(f"{NOTIFICATIONS}/{first_id}/read", headers=driver["headers"])
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert marked.json()["read_at"] is not None

    after = client.get(NOTIFICATIONS, headers=driver["headers"]).json()
    assert after["unread_count"] == max(0, listing["unread_count"] - 1)

    all_read = client.post(f"{NOTIFICATIONS}/read-all", headers=driver["headers"])
    assert all_read.status_code == 200
    assert all_read.json()["marked_read"] == after["unread_count"]
    assert client.get(f"{NOTIFICATIONS}/unread-count", headers=driver["headers"]).json()["unread_count"] == 0

    # idempotent
    assert client.post(f"{NOTIFICATIONS}/read-all", headers=driver["headers"]).json()["marked_read"] == 0


def test_unread_only_filter_and_cursor_pagination(client, db):
    driver, _passenger, _ride, _trip = matched_trip(client)

    # Guarantee a known number of notifications with distinct timestamps.
    from app.models.enums import NotificationType
    from app.models.notification import Notification as NotificationModel

    for index in range(5):
        db.add(
            NotificationModel(
                user_id=uuid.UUID(driver["user"]["id"]),
                type=NotificationType.SYSTEM,
                title=f"Update {index}",
                body="Body",
                created_at=datetime.now(timezone.utc) + timedelta(seconds=index),
            )
        )
    db.commit()

    page = client.get(f"{NOTIFICATIONS}?limit=2", headers=driver["headers"]).json()
    assert page["count"] == 2
    assert page["next_cursor"]
    second = client.get(
        f"{NOTIFICATIONS}?limit=2&cursor={page['next_cursor']}", headers=driver["headers"]
    ).json()
    assert second["count"] == 2
    assert {item["id"] for item in page["items"]} & {item["id"] for item in second["items"]} == set()

    unread = client.get(f"{NOTIFICATIONS}?unread_only=true", headers=driver["headers"]).json()
    assert all(item["is_read"] is False for item in unread["items"])

    client.post(f"{NOTIFICATIONS}/read-all", headers=driver["headers"])
    assert client.get(f"{NOTIFICATIONS}?unread_only=true", headers=driver["headers"]).json()["count"] == 0


def test_invalid_cursor_is_rejected(client):
    driver, *_ = matched_trip(client)
    assert client.get(f"{NOTIFICATIONS}?cursor=garbage", headers=driver["headers"]).status_code == 422


# ------------------------------------------------------------------- devices
def test_device_registration_lifecycle(client):
    user = register(client)
    token = "ExponentPushToken[abcdefgh12345678]"

    created = client.post(
        f"{NOTIFICATIONS}/devices", json={"token": token, "platform": "android"}, headers=user["headers"]
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is True

    devices = client.get(f"{NOTIFICATIONS}/devices", headers=user["headers"]).json()
    assert len(devices) == 1

    # registering the same token again is idempotent, not a duplicate row
    again = client.post(
        f"{NOTIFICATIONS}/devices", json={"token": token, "platform": "android"}, headers=user["headers"]
    )
    assert again.status_code == 201
    assert len(client.get(f"{NOTIFICATIONS}/devices", headers=user["headers"]).json()) == 1

    removed = client.delete(f"{NOTIFICATIONS}/devices/{token}", headers=user["headers"])
    assert removed.status_code == 200
    devices = client.get(f"{NOTIFICATIONS}/devices", headers=user["headers"]).json()
    assert devices[0]["is_active"] is False

    assert client.delete(f"{NOTIFICATIONS}/devices/{token}", headers=user["headers"]).status_code == 404


def test_token_cannot_be_hijacked_by_another_account(client):
    first = register(client)
    second = register(client)
    token = "ExponentPushToken[movedhandset01]"

    client.post(f"{NOTIFICATIONS}/devices", json={"token": token}, headers=first["headers"])
    client.post(f"{NOTIFICATIONS}/devices", json={"token": token}, headers=second["headers"])

    # the handset now belongs to the second account only
    assert client.get(f"{NOTIFICATIONS}/devices", headers=first["headers"]).json() == []
    assert len(client.get(f"{NOTIFICATIONS}/devices", headers=second["headers"]).json()) == 1

    # …and the first account cannot deactivate it any more
    assert client.delete(f"{NOTIFICATIONS}/devices/{token}", headers=first["headers"]).status_code == 404


def test_short_token_is_rejected(client):
    user = register(client)
    assert (
        client.post(f"{NOTIFICATIONS}/devices", json={"token": "abc"}, headers=user["headers"]).status_code
        == 422
    )


# --------------------------------------------------------------- push payloads
def test_build_messages_skips_already_pushed_and_inactive(client, db):
    user = register(client)
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[active]", platform="android"))
    db.add(
        DeviceToken(
            user_id=uuid.UUID(user["user"]["id"]),
            token="ExponentPushToken[inactive]",
            platform="android",
            is_active=False,
        )
    )
    db.add(
        Notification(
            user_id=uuid.UUID(user["user"]["id"]),
            type="SYSTEM",
            title="Hello",
            body="World",
            data={"screen": "home"},
        )
    )
    db.commit()

    notification = db.scalar(select(Notification).where(Notification.title == "Hello"))
    payloads = push_service.build_messages(db, [notification])
    assert len(payloads) == 1  # inactive device skipped
    assert payloads[0]["to"] == "ExponentPushToken[active]"
    assert payloads[0]["title"] == "Hello"
    assert payloads[0]["data"]["notification_id"] == str(notification.id)
    assert payloads[0]["data"]["screen"] == "home"

    notification.push_sent_at = datetime.now(timezone.utc)
    db.commit()
    assert push_service.build_messages(db, [notification]) == []


def test_dispatch_marks_sent_and_deactivates_dead_tokens(client, db, monkeypatch):
    user = register(client)
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[good]", platform="android"))
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[dead]", platform="android"))
    db.add(Notification(user_id=uuid.UUID(user["user"]["id"]), type="SYSTEM", title="Trip update", body="Body"))
    db.commit()
    notification = db.scalar(select(Notification).where(Notification.title == "Trip update"))

    sent: list[list[dict]] = []

    def fake_send(payloads):
        sent.append(payloads)
        return [
            {"status": "ok", "id": "ticket-1"},
            {"status": "error", "message": "not registered", "details": {"error": "DeviceNotRegistered"}},
        ]

    monkeypatch.setattr(push_service, "_send_batches", fake_send)
    monkeypatch.setattr(push_service.settings, "ENVIRONMENT", "development")

    result = push_service.dispatch(db, [notification])

    assert len(sent) == 1
    assert result.attempted == 2
    assert result.sent == 2
    assert result.deactivated_tokens == ["ExponentPushToken[dead]"]
    db.refresh(notification)
    assert notification.push_sent_at is not None

    dead = db.scalar(select(DeviceToken).where(DeviceToken.token == "ExponentPushToken[dead]"))
    assert dead.is_active is False
    good = db.scalar(select(DeviceToken).where(DeviceToken.token == "ExponentPushToken[good]"))
    assert good.is_active is True


def test_dispatch_survives_network_failure(client, db, monkeypatch):
    user = register(client)
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[any]", platform="android"))
    db.add(Notification(user_id=uuid.UUID(user["user"]["id"]), type="SYSTEM", title="Boom", body="Body"))
    db.commit()
    notification = db.scalar(select(Notification).where(Notification.title == "Boom"))

    def explode(payloads):
        raise RuntimeError("expo is down")

    monkeypatch.setattr(push_service, "_send_batches", explode)
    monkeypatch.setattr(push_service.settings, "ENVIRONMENT", "development")

    result = push_service.dispatch(db, [notification])
    assert result.sent == 0
    assert result.errors and "expo is down" in result.errors[0]
    db.refresh(notification)
    assert notification.push_sent_at is None  # will be retried by a later flush


def test_push_is_queued_and_flushed_after_commit(client, db, monkeypatch):
    """A notification written inside a transaction is only pushed once it commits."""
    user = register(client)
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[postcommit]", platform="android"))
    db.commit()

    calls: list[list[dict]] = []
    monkeypatch.setattr(push_service, "_send_batches", lambda payloads: calls.append(payloads) or [{"status": "ok"}])
    monkeypatch.setattr(push_service.settings, "ENVIRONMENT", "development")

    from app.services.notification_service import create_notification

    create_notification(
        db,
        user_id=uuid.UUID(user["user"]["id"]),
        type=NotificationType.SYSTEM,
        title="Queued",
        body="Should be pushed after commit",
        commit=True,
    )
    # nothing is sent before the request boundary flushes the queue
    assert calls == []

    push_service.flush_pending(db)
    assert len(calls) == 1, "push must fire exactly once, after the commit"
    assert calls[0][0]["to"] == "ExponentPushToken[postcommit]"

    # flushing again is a no-op
    push_service.flush_pending(db)
    assert len(calls) == 1


def test_push_is_not_a_second_side_effect_on_rollback(client, db, monkeypatch):
    user = register(client)
    db.add(DeviceToken(user_id=uuid.UUID(user["user"]["id"]), token="ExponentPushToken[rolledback]", platform="android"))
    db.commit()

    calls: list[list[dict]] = []
    monkeypatch.setattr(push_service, "_send_batches", lambda payloads: calls.append(payloads) or [{"status": "ok"}])
    monkeypatch.setattr(push_service.settings, "ENVIRONMENT", "development")

    from app.services.notification_service import create_notification

    create_notification(
        db,
        user_id=uuid.UUID(user["user"]["id"]),
        type=NotificationType.SYSTEM,
        title="Never happened",
        body="Rolled back",
        commit=False,
    )
    db.rollback()
    push_service.flush_pending(db)
    assert calls == [], "a rolled-back notification must never be pushed"


@pytest.mark.parametrize("trigger", ["chat", "trip"])
def test_in_app_notification_exists_for_chat_and_trip_events(client, trigger):
    driver, passenger, _ride, trip = matched_trip(client)
    if trigger == "chat":
        conversation_id = trip["conversation_id"]
        client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"body": "Salam"},
            headers=driver["headers"],
        )
        expected = "NEW_MESSAGE"
        viewer = passenger
    else:
        client.post(f"/api/v1/trips/{trip['id']}/start", headers=driver["headers"])
        expected = "TRIP_STARTED"
        viewer = passenger

    listing = client.get(NOTIFICATIONS, headers=viewer["headers"]).json()
    assert any(item["type"] == expected for item in listing["items"])


def test_send_batches_authenticates_with_expo_access_token(monkeypatch):
    """Enhanced push security projects reject unauthenticated sends (§12)."""
    captured: list[dict] = []

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"status": "ok", "id": "ticket-1"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured.append({"url": url, "headers": dict(headers or {})})
            return _Response()

    monkeypatch.setattr(push_service.httpx, "Client", _Client)

    monkeypatch.setattr(push_service.settings, "EXPO_ACCESS_TOKEN", "expo-secret")
    tickets = push_service._send_batches([{"to": "ExponentPushToken[good]"}])
    assert tickets == [{"status": "ok", "id": "ticket-1"}]
    assert captured[0]["headers"]["Authorization"] == "Bearer expo-secret"

    captured.clear()
    monkeypatch.setattr(push_service.settings, "EXPO_ACCESS_TOKEN", "  ")
    push_service._send_batches([{"to": "ExponentPushToken[good]"}])
    assert "Authorization" not in captured[0]["headers"]
