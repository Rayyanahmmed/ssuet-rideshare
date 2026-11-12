"""Cash payment, verified transaction and invoice tests (payment feature).

Covers: the driver-only settlement rules, the completion gate, single settlement,
the non-payment report that enters the admin queue, invoice visibility, and the
trip-level flags the mobile app relies on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.enums import PaymentStatus, ReportCategory
from app.models.report import Report
from tests.helpers import passenger_setup, register

TRIPS = "/api/v1/trips"


def iso(**delta) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


def matched_trip(client, *, depart_in_minutes: int = 300, **ride_overrides):
    """Driver + passenger with an accepted request → CONFIRMED trip."""
    driver, _vehicle, ride = passenger_setup(
        client, ride_overrides={"departure_at": iso(minutes=depart_in_minutes), **ride_overrides}
    )
    passenger = register(client)
    response = client.post(
        f"/api/v1/rides/{ride['id']}/requests", json={"message": "Salam!"}, headers=passenger["headers"]
    )
    assert response.status_code == 201, response.text
    inbox = client.get("/api/v1/requests/inbox", headers=driver["headers"]).json()
    request_id = next(item["id"] for item in inbox if item["ride_id"] == ride["id"])
    trip = client.post(f"/api/v1/requests/{request_id}/accept", headers=driver["headers"])
    assert trip.status_code == 200, trip.text
    return driver, passenger, trip.json()


def completed_trip(client):
    """Both sides travel and confirm → COMPLETED trip."""
    driver, passenger, trip = matched_trip(client)
    assert client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"]).status_code == 200
    assert client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"]).status_code == 200
    done = client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"])
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED", done.text
    return driver, passenger, trip["id"]


# ------------------------------------------------------------ confirm (verified)
def test_driver_confirms_cash_and_an_invoice_is_issued(client):
    driver, passenger, trip_id = completed_trip(client)

    response = client.post(
        f"{TRIPS}/{trip_id}/payment/confirm", json={"amount_pkr": 150}, headers=driver["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "VERIFIED"
    assert body["amount_pkr"] == 150
    assert body["invoice_number"].startswith("SRS-")
    assert body["verified_at"] is not None

    trip = client.get(f"{TRIPS}/{trip_id}", headers=passenger["headers"]).json()
    assert trip["payment_status"] == "VERIFIED"
    assert trip["invoice_number"] == body["invoice_number"]
    assert trip["can_confirm_payment"] is False
    assert trip["can_report_non_payment"] is False


def test_passenger_is_told_the_payment_is_verified(client):
    driver, passenger, trip_id = completed_trip(client)
    client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"])

    inbox = client.get("/api/v1/notifications", headers=passenger["headers"]).json()
    assert any(item["title"] == "Payment verified" for item in inbox["items"])


def test_amount_is_optional_and_must_not_be_negative(client):
    driver, _passenger, trip_id = completed_trip(client)

    negative = client.post(
        f"{TRIPS}/{trip_id}/payment/confirm", json={"amount_pkr": -5}, headers=driver["headers"]
    )
    assert negative.status_code == 422

    bare = client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"])
    assert bare.status_code == 200 and bare.json()["amount_pkr"] is None


def test_passenger_cannot_confirm_their_own_payment(client):
    _driver, passenger, trip_id = completed_trip(client)
    response = client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=passenger["headers"])
    assert response.status_code == 403


def test_payment_cannot_be_recorded_before_the_trip_is_completed(client):
    driver, _passenger, trip = matched_trip(client)
    response = client.post(f"{TRIPS}/{trip['id']}/payment/confirm", headers=driver["headers"])
    assert response.status_code == 409


def test_a_settled_payment_cannot_be_confirmed_twice(client):
    driver, _passenger, trip_id = completed_trip(client)
    assert client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"]).status_code == 200
    again = client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"])
    assert again.status_code == 409


# ----------------------------------------------------------- non-payment report
def test_driver_reports_non_payment_and_the_admin_queue_receives_it(client, admin, db):
    driver, passenger, trip_id = completed_trip(client)

    response = client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "Passenger did not pay the agreed fuel share in cash after the trip."},
        headers=driver["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "NON_PAYMENT_REPORTED"
    assert body["non_payment_report_id"] is not None
    assert body["invoice_number"] is None

    report = db.get(Report, uuid.UUID(body["non_payment_report_id"]))
    assert report is not None
    assert report.category is ReportCategory.NON_PAYMENT
    assert str(report.reporter_id) == driver["user"]["id"]
    assert str(report.reported_user_id) == passenger["user"]["id"]

    queue = client.get("/api/v1/admin/reports?category=NON_PAYMENT", headers=admin["headers"]).json()
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == body["non_payment_report_id"]


def test_only_the_driver_can_report_non_payment(client):
    _driver, passenger, trip_id = completed_trip(client)
    response = client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "The passenger tries to report their own payment."},
        headers=passenger["headers"],
    )
    assert response.status_code == 403


def test_non_payment_report_needs_a_real_description(client):
    driver, _passenger, trip_id = completed_trip(client)
    response = client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report", json={"description": "no"}, headers=driver["headers"]
    )
    assert response.status_code == 422


def test_a_reported_payment_cannot_be_verified_afterwards(client):
    driver, _passenger, trip_id = completed_trip(client)
    client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "Passenger did not pay after the journey."},
        headers=driver["headers"],
    )
    assert client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"]).status_code == 409
    again = client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "Reporting the same passenger a second time."},
        headers=driver["headers"],
    )
    assert again.status_code == 409


def test_a_verified_payment_cannot_be_reported_as_non_payment(client):
    driver, _passenger, trip_id = completed_trip(client)
    client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"])
    response = client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "This should be refused because it was paid."},
        headers=driver["headers"],
    )
    assert response.status_code == 409


# ---------------------------------------------------------------- invoice access
def test_invoice_is_visible_to_both_participants_after_verification(client):
    driver, passenger, trip_id = completed_trip(client)
    client.post(f"{TRIPS}/{trip_id}/payment/confirm", json={"amount_pkr": 200}, headers=driver["headers"])

    for member in (driver, passenger):
        response = client.get(f"{TRIPS}/{trip_id}/invoice", headers=member["headers"])
        assert response.status_code == 200, response.text
        invoice = response.json()
        assert invoice["invoice_number"].startswith("SRS-")
        assert invoice["payment_method"] == "CASH"
        assert invoice["amount_pkr"] == 200
        assert invoice["driver_name"] and invoice["passenger_name"]


def test_no_invoice_before_verification(client):
    driver, _passenger, trip_id = completed_trip(client)
    assert client.get(f"{TRIPS}/{trip_id}/invoice", headers=driver["headers"]).status_code == 404


def test_no_invoice_for_a_non_payment_report(client):
    driver, _passenger, trip_id = completed_trip(client)
    client.post(
        f"{TRIPS}/{trip_id}/payment/non-payment-report",
        json={"description": "Passenger did not pay after the journey."},
        headers=driver["headers"],
    )
    assert client.get(f"{TRIPS}/{trip_id}/invoice", headers=driver["headers"]).status_code == 404


def test_outsiders_cannot_read_payment_or_invoice(client):
    driver, _passenger, trip_id = completed_trip(client)
    client.post(f"{TRIPS}/{trip_id}/payment/confirm", headers=driver["headers"])
    outsider = register(client)
    assert client.get(f"{TRIPS}/{trip_id}/payment", headers=outsider["headers"]).status_code == 403
    assert client.get(f"{TRIPS}/{trip_id}/invoice", headers=outsider["headers"]).status_code == 403


# ---------------------------------------------------------------- flags on a trip
def test_driver_sees_the_settle_actions_only_after_completion(client):
    driver, passenger, trip = matched_trip(client)
    before = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    assert before["can_confirm_payment"] is False
    assert before["payment_status"] is None

    client.post(f"{TRIPS}/{trip['id']}/start", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=driver["headers"])
    client.post(f"{TRIPS}/{trip['id']}/complete", headers=passenger["headers"])

    driver_view = client.get(f"{TRIPS}/{trip['id']}", headers=driver["headers"]).json()
    passenger_view = client.get(f"{TRIPS}/{trip['id']}", headers=passenger["headers"]).json()
    assert driver_view["can_confirm_payment"] is True
    assert driver_view["can_report_non_payment"] is True
    assert passenger_view["can_confirm_payment"] is False
    assert passenger_view["can_report_non_payment"] is False


def test_payment_status_endpoint_defaults_to_pending(client):
    driver, _passenger, trip_id = completed_trip(client)
    response = client.get(f"{TRIPS}/{trip_id}/payment", headers=driver["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == PaymentStatus.PENDING.value
