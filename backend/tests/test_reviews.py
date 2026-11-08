"""Phase 7 — ratings & reviews (§14).

The review system is the trust backbone of a pooling app where no money changes
hands, so these tests concentrate on the constraints: completed trips only,
participants only, one review per side, aggregates that can never drift, and a
moderation path that actually changes the average.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.review import Review
from app.models.user import User
from tests.helpers import passenger_setup, register


def iso(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def completed_trip(client, *, review: bool = False, **kwargs):
    """A full happy path: publish → request → accept → start → both confirm.

    Returns `(driver, passenger, ride, trip)`; `review=True` rates it from both
    sides so the aggregate assertions have something to look at.
    """
    driver, _vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=10)}, **kwargs
    )
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(
        f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]
    ).json()
    client.post(f"/api/v1/trips/{trip['id']}/start", headers=driver["headers"])
    client.post(f"/api/v1/trips/{trip['id']}/complete", headers=driver["headers"])
    client.post(f"/api/v1/trips/{trip['id']}/complete", headers=passenger["headers"])
    if review:
        client.post(
            f"/api/v1/reviews/trips/{trip['id']}",
            json={"rating": 5, "comment": "Smooth ride, on time."},
            headers=passenger["headers"],
        )
        client.post(
            f"/api/v1/reviews/trips/{trip['id']}",
            json={"rating": 4, "comment": "Polite and punctual."},
            headers=driver["headers"],
        )
    return driver, passenger, ride, trip


# --------------------------------------------------------------------- create
def test_passenger_can_rate_the_driver(client):
    driver, passenger, _ride, trip = completed_trip(client)

    response = client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "  Great   company,   always on time.  "},
        headers=passenger["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rating"] == 5
    assert body["comment"] == "Great company, always on time."  # whitespace collapsed
    assert body["subject_id"] == driver["user"]["id"]
    assert body["author"]["id"] == passenger["user"]["id"]
    assert body["pickup_area"] == "Gulshan-e-Iqbal"
    # the author's public summary never carries contact details
    assert "phone" not in body["author"] and "email" not in body["author"]


def test_driver_can_rate_the_passenger(client):
    driver, passenger, _ride, trip = completed_trip(client)
    response = client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 4},
        headers=driver["headers"],
    )
    assert response.status_code == 201
    assert response.json()["subject_id"] == passenger["user"]["id"]
    assert response.json()["comment"] is None


def test_review_updates_the_aggregate_immediately(client, db):
    driver, passenger, _ride, trip = completed_trip(client)
    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 4, "comment": "Fine."},
        headers=passenger["headers"],
    )
    subject = db.get(User, uuid.UUID(driver["user"]["id"]))
    db.refresh(subject)
    assert subject.rating_count == 1
    assert subject.rating_average == 4.0

    # the public profile reflects it too
    profile = client.get(
        f"/api/v1/users/{driver['user']['id']}/public", headers=passenger["headers"]
    ).json()
    assert profile["rating_count"] == 1 and profile["rating_average"] == 4.0


def test_second_review_of_the_same_trip_is_refused(client):
    driver, passenger, _ride, trip = completed_trip(client)
    payload = {"rating": 5, "comment": "Lovely."}
    first = client.post(
        f"/api/v1/reviews/trips/{trip['id']}", json=payload, headers=passenger["headers"]
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/reviews/trips/{trip['id']}", json=payload, headers=passenger["headers"]
    )
    assert second.status_code == 409
    assert "already rated" in second.json()["error"]["message"].lower()


def test_both_sides_may_review_the_same_trip_once_each(client):
    driver, passenger, _ride, trip = completed_trip(client, review=True)
    received_by_driver = client.get(
        f"/api/v1/reviews/users/{driver['user']['id']}", headers=driver["headers"]
    ).json()
    received_by_passenger = client.get(
        f"/api/v1/reviews/users/{passenger['user']['id']}", headers=driver["headers"]
    ).json()
    assert received_by_driver["total"] == 1
    assert received_by_passenger["total"] == 1


def test_incomplete_trip_cannot_be_reviewed(client):
    driver, _vehicle, ride = passenger_setup(client, ride_overrides={"departure_at": iso(minutes=10)})
    passenger = register(client)
    client.post(f"/api/v1/rides/{ride['id']}/requests", json={}, headers=passenger["headers"])
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"]).json()

    for headers in (driver["headers"], passenger["headers"]):
        response = client.post(
            f"/api/v1/reviews/trips/{trip['id']}", json={"rating": 5}, headers=headers
        )
        assert response.status_code == 409
        assert "completed" in response.json()["error"]["message"].lower()


def test_outsider_cannot_review_a_trip(client):
    _driver, _passenger, _ride, trip = completed_trip(client)
    intruder = register(client)
    response = client.post(
        f"/api/v1/reviews/trips/{trip['id']}", json={"rating": 1}, headers=intruder["headers"]
    )
    assert response.status_code == 403


def test_unknown_trip_is_404(client):
    member = register(client)
    response = client.post(
        f"/api/v1/reviews/trips/{uuid.uuid4()}", json={"rating": 5}, headers=member["headers"]
    )
    assert response.status_code == 404


def test_review_requires_authentication(client):
    assert client.post(f"/api/v1/reviews/trips/{uuid.uuid4()}", json={"rating": 5}).status_code == 401


@pytest.mark.parametrize("rating", [0, 6, -1, 10])
def test_rating_must_be_between_one_and_five(client, rating):
    _driver, passenger, _ride, trip = completed_trip(client)
    response = client.post(
        f"/api/v1/reviews/trips/{trip['id']}", json={"rating": rating}, headers=passenger["headers"]
    )
    assert response.status_code == 422


def test_comment_length_is_bounded(client):
    _driver, passenger, _ride, trip = completed_trip(client)
    too_long = client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "x" * 501},
        headers=passenger["headers"],
    )
    assert too_long.status_code == 422

    too_short = client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "ok"},
        headers=passenger["headers"],
    )
    assert too_short.status_code == 422


def test_reviewing_notifies_the_subject(client):
    driver, passenger, _ride, trip = completed_trip(client)
    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "Excellent driver."},
        headers=passenger["headers"],
    )
    inbox = client.get("/api/v1/notifications", headers=driver["headers"]).json()
    review_notes = [item for item in inbox["items"] if item["type"] == "NEW_REVIEW"]
    assert review_notes
    assert review_notes[0]["data"]["trip_id"] == trip["id"]


# ----------------------------------------------------------------------- read
def test_review_page_includes_distribution(client):
    driver, passenger, _ride, trip = completed_trip(client)
    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 4, "comment": "Good trip."},
        headers=passenger["headers"],
    )
    body = client.get(
        f"/api/v1/reviews/users/{driver['user']['id']}", headers=passenger["headers"]
    ).json()
    assert body["total"] == 1
    assert body["average"] == 4.0
    assert body["breakdown"] == {"5": 0, "4": 1, "3": 0, "2": 0, "1": 0}
    assert body["pages"] == 1


def test_member_without_reviews_gets_an_empty_page(client):
    member = register(client)
    body = client.get(
        f"/api/v1/reviews/users/{member['user']['id']}", headers=member["headers"]
    ).json()
    assert body["items"] == []
    assert body["average"] == 0.0
    assert body["breakdown"] == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}


def test_reviews_of_unknown_member_are_404(client):
    member = register(client)
    response = client.get(f"/api/v1/reviews/users/{uuid.uuid4()}", headers=member["headers"])
    assert response.status_code == 404


def test_my_received_reviews(client):
    driver, passenger, _ride, trip = completed_trip(client, review=True)
    mine = client.get("/api/v1/reviews/me/received", headers=driver["headers"]).json()
    assert mine["total"] == 1
    assert mine["items"][0]["author"]["id"] == passenger["user"]["id"]


def test_pending_reviews_track_what_is_still_owed(client):
    driver, passenger, _ride, trip = completed_trip(client)

    pending = client.get("/api/v1/reviews/pending", headers=driver["headers"]).json()
    assert pending["count"] == 1
    assert pending["items"][0]["trip_id"] == trip["id"]
    assert pending["items"][0]["counterpart"]["id"] == passenger["user"]["id"]
    assert pending["items"][0]["my_role"] == "DRIVER"

    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "Great passenger."},
        headers=driver["headers"],
    )
    assert client.get("/api/v1/reviews/pending", headers=driver["headers"]).json()["count"] == 0
    # the passenger still owes theirs
    assert client.get("/api/v1/reviews/pending", headers=passenger["headers"]).json()["count"] == 1


def test_trip_payload_exposes_can_review(client):
    driver, passenger, _ride, trip = completed_trip(client)
    payload = client.get(f"/api/v1/trips/{trip['id']}", headers=driver["headers"]).json()
    assert payload["can_review"] is True
    assert payload["viewer_reviewed"] is False

    client.post(
        f"/api/v1/reviews/trips/{trip['id']}",
        json={"rating": 5, "comment": "Good."},
        headers=driver["headers"],
    )
    after = client.get(f"/api/v1/trips/{trip['id']}", headers=driver["headers"]).json()
    assert after["can_review"] is False
    assert after["viewer_reviewed"] is True


# ---------------------------------------------------------------- moderation
def test_hidden_review_leaves_the_public_page_and_the_average(client, db, admin):
    driver, passenger, _ride, trip = completed_trip(client, review=True)
    driver_id = driver["user"]["id"]

    reviews = client.get("/api/v1/reviews/users/" + driver_id, headers=driver["headers"]).json()
    assert reviews["total"] == 1
    review_id = reviews["items"][0]["id"]
    assert reviews["average"] == 5.0

    hidden = client.post(
        f"/api/v1/admin/reviews/{review_id}/hide",
        json={"reason": "Abusive language in the comment"},
        headers=admin["headers"],
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["is_hidden"] is True

    after = client.get("/api/v1/reviews/users/" + driver_id, headers=driver["headers"]).json()
    assert after["total"] == 0
    assert after["average"] == 0.0

    subject = db.get(User, uuid.UUID(driver_id))
    db.refresh(subject)
    assert subject.rating_count == 0 and subject.rating_average == 0.0

    restored = client.post(
        f"/api/v1/admin/reviews/{review_id}/unhide", headers=admin["headers"]
    )
    assert restored.status_code == 200
    assert client.get(
        f"/api/v1/reviews/users/{driver_id}", headers=driver["headers"]
    ).json()["average"] == 5.0


def test_hiding_a_review_twice_conflicts(client, admin):
    driver, _passenger, _ride, _trip = completed_trip(client, review=True)
    reviews = client.get(
        f"/api/v1/reviews/users/{driver['user']['id']}", headers=driver["headers"]
    ).json()
    review_id = reviews["items"][0]["id"]
    assert client.post(f"/api/v1/admin/reviews/{review_id}/hide", headers=admin["headers"]).status_code == 200
    assert client.post(f"/api/v1/admin/reviews/{review_id}/hide", headers=admin["headers"]).status_code == 409


def test_moderation_is_audited_and_admin_only(client, admin, db):
    driver, _passenger, _ride, _trip = completed_trip(client, review=True)
    reviews = client.get(
        f"/api/v1/reviews/users/{driver['user']['id']}", headers=driver["headers"]
    ).json()
    review_id = reviews["items"][0]["id"]

    assert client.post(f"/api/v1/admin/reviews/{review_id}/hide").status_code == 401

    member = register(client)
    assert (
        client.post(f"/api/v1/admin/reviews/{review_id}/hide", headers=member["headers"]).status_code
        == 403
    )

    client.post(
        f"/api/v1/admin/reviews/{review_id}/hide",
        json={"reason": "Personal attack"},
        headers=admin["headers"],
    )
    log = client.get("/api/v1/admin/admin-actions", headers=admin["headers"]).json()
    assert any(item["action_type"] == "HIDE_REVIEW" for item in log["items"])


def test_admin_review_feed_and_filters(client, admin):
    driver, _passenger, _ride, _trip = completed_trip(client, review=True)

    feed = client.get("/api/v1/admin/reviews", headers=admin["headers"]).json()
    assert feed["total"] == 2

    five_star = client.get("/api/v1/admin/reviews?min_rating=5", headers=admin["headers"]).json()
    assert five_star["total"] == 1
    assert five_star["items"][0]["rating"] == 5

    search = client.get(
        f"/api/v1/admin/reviews?search={driver['user']['full_name'].split(' ')[0]}",
        headers=admin["headers"],
    ).json()
    assert search["total"] >= 1
