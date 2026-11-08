"""Phase 5 — trip chat tests (§11): REST surface plus the WebSocket protocol."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import passenger_setup, register

CHAT = "/api/v1/chat"


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def matched_trip(client, *, depart_in_minutes: int = 300):
    """Driver + passenger + accepted request → trip with a conversation."""
    driver, vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=depart_in_minutes)}
    )
    passenger = register(client)
    created = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={"message": "Salam!"}, headers=passenger["headers"]
    )
    assert created.status_code == 201, created.text
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"])
    assert trip.status_code == 200, trip.text
    body = trip.json()
    assert body["conversation_id"], "accepting a request must open a conversation"
    return driver, passenger, ride, body, body["conversation_id"]


def send(client, conversation_id, headers, body="Hello"):
    return client.post(f"{CHAT}/conversations/{conversation_id}/messages", json={"body": body}, headers=headers)


# ------------------------------------------------------------------- surface
def test_conversation_exists_for_both_participants(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)

    driver_list = client.get(f"{CHAT}/conversations", headers=driver["headers"]).json()
    passenger_list = client.get(f"{CHAT}/conversations", headers=passenger["headers"]).json()
    assert driver_list["count"] == 1 and passenger_list["count"] == 1
    assert driver_list["items"][0]["id"] == conversation_id
    assert passenger_list["items"][0]["counterpart"]["id"] == driver["user"]["id"]
    assert driver_list["items"][0]["counterpart"]["id"] == passenger["user"]["id"]


def test_outsider_cannot_read_or_write(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    outsider = register(client)

    assert client.get(f"{CHAT}/conversations", headers=outsider["headers"]).json()["count"] == 0
    assert client.get(f"{CHAT}/conversations/{conversation_id}", headers=outsider["headers"]).status_code == 403
    assert client.get(f"{CHAT}/conversations/{conversation_id}/messages", headers=outsider["headers"]).status_code == 403
    assert send(client, conversation_id, outsider["headers"]).status_code == 403


def test_unknown_conversation_is_404(client):
    user = register(client)
    missing = uuid.uuid4()
    assert client.get(f"{CHAT}/conversations/{missing}", headers=user["headers"]).status_code == 404


def test_chat_requires_authentication(client):
    _driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    assert client.get(f"{CHAT}/conversations").status_code == 401
    assert send(client, conversation_id, {}).status_code == 401


def test_message_round_trip_updates_preview_and_unread(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)

    response = send(client, conversation_id, driver["headers"], "I am at the main gate")
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["is_mine"] is True
    assert message["sender_id"] == driver["user"]["id"]

    history = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages", headers=passenger["headers"]
    ).json()
    assert history["count"] == 1
    assert history["items"][0]["body"] == "I am at the main gate"
    assert history["items"][0]["is_mine"] is False

    passenger_list = client.get(f"{CHAT}/conversations", headers=passenger["headers"]).json()
    row = passenger_list["items"][0]
    assert row["unread_count"] == 1
    assert row["last_message_preview"] == "I am at the main gate"
    assert row["last_message_is_mine"] is False
    assert passenger_list["unread_total"] == 1


def test_mark_read_clears_unread_and_timestamps_messages(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)
    send(client, conversation_id, driver["headers"], "First")
    send(client, conversation_id, driver["headers"], "Second")

    receipt = client.post(
        f"{CHAT}/conversations/{conversation_id}/read", headers=passenger["headers"]
    )
    assert receipt.status_code == 200
    assert receipt.json()["messages_marked_read"] == 2

    after = client.get(f"{CHAT}/conversations", headers=passenger["headers"]).json()
    assert after["items"][0]["unread_count"] == 0
    assert after["unread_total"] == 0

    driver_view = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages", headers=driver["headers"]
    ).json()
    assert all(item["read_at"] for item in driver_view["items"])

    # marking read twice is harmless
    again = client.post(f"{CHAT}/conversations/{conversation_id}/read", headers=passenger["headers"])
    assert again.json()["messages_marked_read"] == 0


def test_message_cursor_pagination_walks_backwards(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    for index in range(5):
        assert send(client, conversation_id, driver["headers"], f"Message {index}").status_code == 201

    first = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages?limit=2", headers=driver["headers"]
    ).json()
    assert first["count"] == 2
    assert first["items"][0]["body"] == "Message 4"  # newest first
    assert first["next_cursor"]

    second = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages?limit=2&cursor={first['next_cursor']}",
        headers=driver["headers"],
    ).json()
    assert [item["body"] for item in second["items"]] == ["Message 2", "Message 1"]

    third = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages?limit=2&cursor={second['next_cursor']}",
        headers=driver["headers"],
    ).json()
    assert [item["body"] for item in third["items"]] == ["Message 0"]
    assert third["next_cursor"] is None

    invalid = client.get(
        f"{CHAT}/conversations/{conversation_id}/messages?cursor=not-a-cursor", headers=driver["headers"]
    )
    assert invalid.status_code == 422


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
def test_blank_messages_are_rejected(client, body):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    assert send(client, conversation_id, driver["headers"], body).status_code == 422


def test_overlong_message_is_rejected(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    assert send(client, conversation_id, driver["headers"], "x" * 2001).status_code == 422


def test_whitespace_is_trimmed(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    response = send(client, conversation_id, driver["headers"], "   on my way   ")
    assert response.json()["body"] == "on my way"


def test_blocked_pair_cannot_message(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)
    blocked = client.post(f"/api/v1/users/{driver['user']['id']}/block", headers=passenger["headers"])
    assert blocked.status_code in (200, 201), blocked.text

    response = send(client, conversation_id, driver["headers"], "Hello?")
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason_code"] == "BLOCKED"


def test_cancelled_trip_chat_is_read_only(client):
    driver, _passenger, _ride, trip, conversation_id = matched_trip(client)
    client.post(f"/api/v1/trips/{trip['id']}/cancel", json={"reason": "Car trouble"}, headers=driver["headers"])

    response = send(client, conversation_id, driver["headers"], "Sorry!")
    assert response.status_code == 409


# ----------------------------------------------------------------- WebSocket
def ws_url(conversation_id: str, token: str) -> str:
    return f"/api/v1/chat/ws/{conversation_id}?token={token}"


def test_socket_handshake_reports_room_state(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)
    with client.websocket_connect(ws_url(conversation_id, driver["access_token"])) as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        assert ready["conversation_id"] == conversation_id
        assert ready["user_id"] == driver["user"]["id"]
        assert ready["counterpart"]["id"] == passenger["user"]["id"]
        assert {p["role"] for p in ready["participants"]} == {"DRIVER", "PASSENGER"}


def test_socket_delivers_messages_to_both_sides(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)

    with client.websocket_connect(ws_url(conversation_id, driver["access_token"])) as driver_socket:
        driver_socket.receive_json()  # ready

        with client.websocket_connect(ws_url(conversation_id, passenger["access_token"])) as passenger_socket:
            passenger_socket.receive_json()  # ready
            presence = driver_socket.receive_json()  # driver learns the passenger is online
            assert presence["type"] == "presence"
            assert passenger["user"]["id"] in presence["online"]

            passenger_socket.send_json({"type": "message", "body": "I am outside the gate"})
            sender_view = passenger_socket.receive_json()
            receiver_view = driver_socket.receive_json()
            assert sender_view["type"] == "message" and receiver_view["type"] == "message"
            assert receiver_view["message"]["body"] == "I am outside the gate"
            assert receiver_view["message"]["sender_id"] == passenger["user"]["id"]
            assert sender_view["message"]["is_mine"] is True
            assert receiver_view["message"]["is_mine"] is False

            # persisted, so REST history agrees with the socket
            history = client.get(
                f"{CHAT}/conversations/{conversation_id}/messages", headers=driver["headers"]
            ).json()
            assert history["items"][0]["body"] == "I am outside the gate"

            # presence is withdrawn on disconnect
            passenger_socket.close()
            offline = driver_socket.receive_json()
            assert offline["type"] == "presence" and offline["online"] == [driver["user"]["id"]]


def test_socket_relays_typing_and_read_receipts(client):
    driver, passenger, _ride, _trip, conversation_id = matched_trip(client)
    send(client, conversation_id, driver["headers"], "Where are you?")

    with client.websocket_connect(ws_url(conversation_id, driver["access_token"])) as driver_socket:
        driver_socket.receive_json()
        with client.websocket_connect(ws_url(conversation_id, passenger["access_token"])) as passenger_socket:
            passenger_socket.receive_json()
            driver_socket.receive_json()  # presence

            passenger_socket.send_json({"type": "typing", "is_typing": True})
            typing = driver_socket.receive_json()
            assert typing == {
                "type": "typing",
                "user_id": passenger["user"]["id"],
                "is_typing": True,
            }

            passenger_socket.send_json({"type": "read"})
            receipt = driver_socket.receive_json()
            assert receipt["type"] == "read"
            assert receipt["user_id"] == passenger["user"]["id"]
            assert receipt["messages_marked_read"] == 1


def test_socket_rejects_non_participant(client):
    _driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    outsider = register(client)
    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect(ws_url(conversation_id, outsider["access_token"])) as socket:
            socket.receive_json()
    assert getattr(excinfo.value, "code", None) == 1008


def test_socket_rejects_bad_token(client):
    _driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    with pytest.raises(Exception) as excinfo:
        with client.websocket_connect(ws_url(conversation_id, "not-a-jwt")) as socket:
            socket.receive_json()
    assert getattr(excinfo.value, "code", None) == 1008


def test_socket_accepts_authorization_header(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    with client.websocket_connect(
        f"/api/v1/chat/ws/{conversation_id}",
        headers={"Authorization": f"Bearer {driver['access_token']}"},
    ) as socket:
        assert socket.receive_json()["type"] == "ready"


def test_socket_ping_pong_and_unknown_frame(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    with client.websocket_connect(ws_url(conversation_id, driver["access_token"])) as socket:
        socket.receive_json()
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}

        socket.send_json({"type": "dance"})
        error = socket.receive_json()
        assert error["type"] == "error" and error["code"] == "VALIDATION_ERROR"


def test_socket_reports_business_errors_inline(client):
    driver, _passenger, _ride, _trip, conversation_id = matched_trip(client)
    with client.websocket_connect(ws_url(conversation_id, driver["access_token"])) as socket:
        socket.receive_json()
        socket.send_json({"type": "message", "body": "    "})
        error = socket.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "VALIDATION_ERROR"
