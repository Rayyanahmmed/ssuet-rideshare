"""Photo moderation (§15, Phase 15).

A profile picture is the one piece of content in the product that a member publishes
about themselves and everybody else sees. This suite covers the whole loop: a member
complains, the exact file is pinned as evidence, the office decides, and the decision can
take the picture down — without destroying the evidence or letting the queue be flooded.
"""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.enums import ReportStatus
from app.models.media import MediaAsset
from app.models.notification import Notification
from app.models.report import Report
from app.services import media_service
from tests.helpers import register

def png_bytes(size: int = 64, colour=(30, 90, 140)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), colour).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"), raising=False)
    return tmp_path / "media"


@pytest.fixture
def driver(client):
    """The member whose photo will be complained about."""
    body = register(client, email=f"sharer-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    headers = body["headers"]
    uploaded = client.post(
        "/api/v1/users/me/photo", headers=headers, files={"file": ("me.png", png_bytes(), "image/png")}
    )
    assert uploaded.status_code == 201, uploaded.text
    return {"headers": headers, "user": body["user"], "photo_url": uploaded.json()["profile_photo_url"]}


@pytest.fixture
def other(client):
    body = register(client, email=f"bystander-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user": body["user"]}


@pytest.fixture
def reporter(client):
    body = register(client, email=f"reporter-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user": body["user"]}


def file_report(client, reporter, target_id, *, reason="OFFENSIVE", description=None):
    return client.post(
        f"/api/v1/users/{target_id}/photo/report",
        headers=reporter["headers"],
        json={
            "reason": reason,
            "description": description or "This picture is not appropriate for the campus ride-share community.",
        },
    )


# ----------------------------------------------------------------- filing it
def test_a_member_can_report_a_photo(client, reporter, driver):
    response = file_report(client, reporter, driver["user"]["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category"] == "PROFILE_PHOTO"
    assert body["status"] == "OPEN"
    assert body["reported_user"]["id"] == driver["user"]["id"]


def test_the_reported_asset_is_pinned_on_the_report(client, reporter, driver, db):
    file_report(client, reporter, driver["user"]["id"])
    report = db.scalars(select(Report)).one()
    assert report.reported_photo_asset_id is not None
    assert report.photo_reason == "OFFENSIVE"
    assert report.category.value == "PROFILE_PHOTO"


def test_the_reporter_and_the_office_are_both_told(client, reporter, driver, db, admin):
    file_report(client, reporter, driver["user"]["id"])

    reporter_notes = db.scalars(
        select(Notification).where(Notification.user_id == uuid.UUID(reporter["user"]["id"]))
    ).all()
    assert any("report" in n.title.lower() for n in reporter_notes)

    admin_notes = db.scalars(
        select(Notification).where(Notification.user_id == uuid.UUID(admin["user"]["id"]))
    ).all()
    assert any("photo reported" in n.title.lower() for n in admin_notes)


def test_a_second_open_report_is_refused(client, reporter, driver):
    assert file_report(client, reporter, driver["user"]["id"]).status_code == 201
    second = file_report(client, reporter, driver["user"]["id"])
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_two_members_may_report_the_same_photo(client, reporter, driver, other):
    assert file_report(client, reporter, driver["user"]["id"]).status_code == 201
    assert file_report(client, other, driver["user"]["id"]).status_code == 201


def test_reporting_your_own_photo_is_refused(client, driver):
    response = file_report(client, driver, driver["user"]["id"])
    assert response.status_code == 422
    assert "upload another one" in response.json()["error"]["message"].lower()


def test_reporting_a_member_without_a_photo_is_a_404(client, reporter):
    body = register(client, email=f"nophoto-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    response = file_report(client, reporter, body["user"]["id"])
    assert response.status_code == 404


def test_an_unknown_member_is_a_404(client, reporter):
    assert file_report(client, reporter, str(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize(
    ("reason", "description"),
    [
        ("NOT_A_REAL", "This is not a photo of a person at all, just a logo."),
        ("OFFENSIVE", "too short"),
    ],
)
def test_the_payload_is_validated(client, reporter, driver, reason, description):
    response = client.post(
        f"/api/v1/users/{driver['user']['id']}/photo/report",
        headers=reporter["headers"],
        json={"reason": reason, "description": description},
    )
    assert response.status_code == 422


def test_reporting_requires_a_session(client, driver):
    response = client.post(
        f"/api/v1/users/{driver['user']['id']}/photo/report",
        json={"reason": "OFFENSIVE", "description": "Anonymous attempts must not reach the queue."},
    )
    assert response.status_code == 401


# --------------------------------------------------------------- the queue
def test_the_admin_queue_shows_the_reason_and_the_evidence(client, reporter, driver, admin):
    file_report(client, reporter, driver["user"]["id"])
    listing = client.get("/api/v1/admin/reports", headers=admin["headers"], params={"status": "OPEN"})
    assert listing.status_code == 200
    row = next(item for item in listing.json()["items"] if item["category"] == "PROFILE_PHOTO")
    assert row["photo_reason"] == "OFFENSIVE"
    assert row["reported_photo_url"].startswith("/api/v1/media/")

    evidence = client.get(row["reported_photo_url"], headers=admin["headers"])
    assert evidence.status_code == 200
    assert evidence.headers["content-type"] == "image/webp"


def test_the_queue_can_be_filtered_to_photo_reports(client, reporter, driver, admin):
    file_report(client, reporter, driver["user"]["id"])
    filtered = client.get(
        "/api/v1/admin/reports", headers=admin["headers"], params={"category": "PROFILE_PHOTO"}
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert all(item["category"] == "PROFILE_PHOTO" for item in filtered.json()["items"])


# ------------------------------------------------------------- the decision
def test_resolving_with_remove_photo_takes_the_picture_down(client, reporter, driver, admin, db):
    report_id = file_report(client, reporter, driver["user"]["id"]).json()["id"]

    resolved = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "RESOLVED", "resolution_note": "Removed the picture.", "remove_photo": True},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"

    assert client.get("/api/v1/users/me", headers=driver["headers"]).json()["profile_photo_url"] is None
    assert client.get(f"/api/v1/users/{driver['user']['id']}/photo", headers=admin["headers"]).status_code == 404

    db.expire_all()
    notes = db.scalars(
        select(Notification).where(Notification.user_id == uuid.UUID(driver["user"]["id"]))
    ).all()
    assert any("photo removed" in n.title.lower() for n in notes), "the member is told what happened"


def test_the_evidence_survives_the_removal(client, reporter, driver, admin):
    """Deleting the complaint's subject would make the decision unauditable."""
    report_id = file_report(client, reporter, driver["user"]["id"]).json()["id"]
    row = next(
        item
        for item in client.get(
            "/api/v1/admin/reports", headers=admin["headers"], params={"category": "PROFILE_PHOTO"}
        ).json()["items"]
    )
    client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "RESOLVED", "resolution_note": "Removed.", "remove_photo": True},
    )
    evidence = client.get(row["reported_photo_url"], headers=admin["headers"])
    assert evidence.status_code == 200, "the reported file must still be readable by an administrator"


def test_a_member_who_replaces_a_reported_photo_does_not_destroy_the_evidence(client, reporter, driver, admin, db):
    report_id = file_report(client, reporter, driver["user"]["id"]).json()["id"]
    first_asset = db.scalars(select(Report)).one().reported_photo_asset_id

    replaced = client.post(
        "/api/v1/users/me/photo",
        headers=driver["headers"],
        files={"file": ("new.png", png_bytes(colour=(200, 20, 20)), "image/png")},
    )
    assert replaced.status_code == 201

    db.expire_all()
    assert db.get(MediaAsset, first_asset) is not None, "the reported file is kept as evidence"
    assert client.get(f"/api/v1/media/{first_asset}", headers=admin["headers"]).status_code == 200

    # ...and the queue still resolves normally afterwards.
    resolved = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "RESOLVED", "resolution_note": "Looked at both photos.", "remove_photo": True},
    )
    assert resolved.status_code == 200


def test_the_sweep_keeps_a_reported_file(client, reporter, driver, db):
    file_report(client, reporter, driver["user"]["id"])
    result = media_service.sweep_orphans(db, older_than_days=0)
    assert result.deleted == 0
    assert result.kept_referenced >= 1


def test_dismissing_leaves_the_photo_alone(client, reporter, driver, admin):
    report_id = file_report(client, reporter, driver["user"]["id"]).json()["id"]
    dismissed = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "DISMISSED", "resolution_note": "A normal profile photo."},
    )
    assert dismissed.status_code == 200
    me = client.get("/api/v1/users/me", headers=driver["headers"]).json()
    assert me["profile_photo_url"] == driver["photo_url"]


def test_remove_photo_on_an_ordinary_report_is_refused(client, reporter, driver, admin):
    trip_report = client.post(
        "/api/v1/reports",
        headers=reporter["headers"],
        json={
            "category": "OTHER",
            "description": "A general complaint that has nothing to do with a picture.",
            "reported_user_id": driver["user"]["id"],
        },
    )
    assert trip_report.status_code == 201, trip_report.text
    report_id = trip_report.json()["id"]
    response = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "RESOLVED", "resolution_note": "Handled.", "remove_photo": True},
    )
    assert response.status_code == 422
    assert "photo report" in response.json()["error"]["message"].lower()


def test_a_resolved_report_is_no_longer_open(client, reporter, driver, admin, db):
    report_id = file_report(client, reporter, driver["user"]["id"]).json()["id"]
    client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=admin["headers"],
        json={"status": "RESOLVED", "resolution_note": "Handled."},
    )
    db.expire_all()
    assert db.get(Report, uuid.UUID(report_id)).status is ReportStatus.RESOLVED
    # And the same member may file a fresh complaint about a new picture.
    assert client.post(
        "/api/v1/users/me/photo",
        headers=driver["headers"],
        files={"file": ("again.png", png_bytes(colour=(90, 20, 200)), "image/png")},
    ).status_code == 201
    assert file_report(client, reporter, driver["user"]["id"]).status_code == 201
