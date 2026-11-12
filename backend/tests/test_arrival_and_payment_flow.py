"""Meeting and payment flow: driver arrival, passenger "payment done", driver verify/report,
and the report categories for miscommitment and scam.

The order is: driver confirms the journey is finished → passenger marks the cash paid →
driver verifies the cash (invoice issued) or reports that it was not paid.
"""

from __future__ import annotations

import pytest

from app.models.enums import NotificationType
from app.models.notification import Notification
from tests.test_payments import TRIPS, matched_trip

NOTIFICATIONS = "/api/v1/notifications"


def finish_by_driver(client, driver, trip_id):
    """Start the trip and let only the driver confirm it is finished."""
    assert client.post(f"{TRIPS}/{trip_id}/start", headers=driver["headers"]).status_code == 200
    response = client.post(f"{TRIPS}/{trip_id}/complete", headers=driver["headers"])
    assert response.status_code == 200, response.text


# ----------------------------------------------------------------- driver arrival
def test_arrival_is_refused_too_early(client):
    driver, _passenger, trip = matched_trip(client, depart_in_minutes=300)
    response = client.post(f"{TRIPS}/{trip['id']}/arrived", headers=driver["headers"])
    assert response.status_code == 409
    flags = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    assert flags["can_mark_arrived"] is False


def test_driver_marks_arrival_and_passenger_is_notified(client):
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)

    flags = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    assert flags["can_mark_arrived"] is True

    response = client.post(f"{TRIPS}/{trip['id']}/arrived", headers=driver["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["driver_arrived_at"] is not None
    assert body["can_mark_arrived"] is False

    # Calling it again changes nothing.
    again = client.post(f"{TRIPS}/{trip['id']}/arrived", headers=driver["headers"])
    assert again.status_code == 200
    assert again.json()["driver_arrived_at"] == body["driver_arrived_at"]

    inbox = client.get(NOTIFICATIONS, headers=passenger["headers"]).json()
    assert any(item["title"] == "Driver has arrived" for item in inbox["items"])

    seen_by_passenger = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert seen_by_passenger["driver_arrived_at"] is not None
    assert seen_by_passenger["can_mark_arrived"] is False


def test_only_the_driver_can_mark_arrival(client):
    _driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    response = client.post(f"{TRIPS}/{trip['id']}/arrived", headers=passenger["headers"])
    assert response.status_code == 403


# ------------------------------------------------------- passenger "payment done"
def test_passenger_cannot_mark_paid_before_driver_finishes(client):
    _driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    response = client.post(f"{TRIPS}/{trip['id']}/payment/mark-paid", headers=passenger["headers"])
    assert response.status_code == 409


def test_payment_done_opens_when_driver_finishes_and_driver_verifies(client):
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    finish_by_driver(client, driver, trip["id"])

    # Passenger view: the button is now available.
    view = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert view["status"] == "IN_PROGRESS"
    assert view["can_mark_paid"] is True

    marked = client.post(f"{TRIPS}/{trip['id']}/payment/mark-paid", headers=passenger["headers"])
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "PAID_BY_PASSENGER"
    assert marked.json()["invoice_number"] is None  # no invoice until the driver verifies

    # Passenger cannot mark it twice; the driver is told.
    twice = client.post(f"{TRIPS}/{trip['id']}/payment/mark-paid", headers=passenger["headers"])
    assert twice.status_code == 409
    driver_inbox = client.get(NOTIFICATIONS, headers=driver["headers"]).json()
    assert any(item["title"] == "Payment marked as done" for item in driver_inbox["items"])

    # Driver sees the confirm action, then verifies the cash.
    driver_view = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    assert driver_view["payment_status"] == "PAID_BY_PASSENGER"
    assert driver_view["can_confirm_payment"] is True
    assert driver_view["can_mark_paid"] is False

    verified = client.post(
        f"{TRIPS}/{trip['id']}/payment/confirm",
        json={"amount_pkr": 120},
        headers=driver["headers"],
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED"
    assert verified.json()["invoice_number"].startswith("SRS-")

    invoice = client.get(f"{TRIPS}/{trip['id']}/invoice", headers=passenger["headers"])
    assert invoice.status_code == 200


def test_driver_can_report_non_payment_after_passenger_says_paid(client):
    """Scam check: if the passenger claims payment that never arrived, the driver reports it."""
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    finish_by_driver(client, driver, trip["id"])
    client.post(f"{TRIPS}/{trip['id']}/payment/mark-paid", headers=passenger["headers"])

    report = client.post(
        f"{TRIPS}/{trip['id']}/payment/non-payment-report",
        json={"description": "The passenger said they paid but no cash was received."},
        headers=driver["headers"],
    )
    assert report.status_code == 201, report.text
    assert report.json()["status"] == "NON_PAYMENT_REPORTED"
    assert client.get(f"{TRIPS}/{trip['id']}/invoice", headers=driver["headers"]).status_code == 404


def test_the_passenger_cannot_verify_their_own_payment(client):
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    finish_by_driver(client, driver, trip["id"])
    client.post(f"{TRIPS}/{trip['id']}/payment/mark-paid", headers=passenger["headers"])
    response = client.post(f"{TRIPS}/{trip['id']}/payment/confirm", headers=passenger["headers"])
    assert response.status_code == 403


# ------------------------------------------------- miscommitment and scam reports
@pytest.mark.parametrize("category", ["MISCOMMITMENT", "SCAM_OR_FRAUD"])
def test_miscommitment_and_scam_reports_are_accepted_during_a_live_trip(client, category):
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])

    response = client.post(
        "/api/v1/reports",
        json={
            "category": category,
            "description": "The member did not keep the agreed pickup and fuel terms.",
            "trip_id": trip["id"],
        },
        headers=passenger["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["category"] == category


def test_notifications_have_the_new_types(client, db):
    driver, passenger, trip = matched_trip(client, depart_in_minutes=20)
    client.post(f"{TRIPS}/{trip['id']}/arrived", headers=driver["headers"])
    types = {row.type for row in db.query(Notification).all()}
    assert NotificationType.DRIVER_ARRIVED in types
