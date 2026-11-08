"""Media housekeeping and vehicle documents (§5, §16, Phase 10).

Two things are proved here:

* the **sweep** deletes only uploads that nothing references, and only after the
  retention window — a member who is mid-flow is never punished;
* a **vehicle** can carry uploaded photo/registration documents instead of external
  links, with the same ownership rules as verification documents.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.media import PURPOSE_VEHICLE_DOCUMENT, MediaAsset
from app.models.vehicle import Vehicle
from app.services import media_service
from tests.helpers import auth_header, register
from tests.test_uploads import JPEG, PNG_1PX

# --------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(root), raising=False)
    return root


@pytest.fixture
def driver(client):
    body = register(client, email=f"driver-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user_id": body["user"]["id"], "token": body["access_token"]}


def upload(client, headers, *, endpoint="/uploads/vehicle", data=PNG_1PX, name="car.png"):
    response = client.post(
        f"/api/v1{endpoint}",
        files={"file": (name, data, "image/png")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def vehicle_payload(**overrides) -> dict:
    suffix = uuid.uuid4().hex[:5].upper()
    payload = {
        "vehicle_type": "CAR",
        "make_and_model": "Suzuki Alto 2021",
        "color": "Silver",
        "registration_number": f"PH10-{suffix}",
        "passenger_capacity": 1,
    }
    payload.update(overrides)
    return payload


def backdate(db, asset_id: str, days: int) -> None:
    asset = db.get(MediaAsset, uuid.UUID(asset_id))
    asset.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.commit()


# ------------------------------------------------------- vehicle upload flow
def test_vehicle_upload_is_tagged_with_its_own_purpose(client, driver):
    asset = upload(client, driver["headers"])
    assert asset["purpose"] == PURPOSE_VEHICLE_DOCUMENT
    assert asset["content_type"] == "image/png"


def test_vehicle_can_carry_uploaded_photo_and_registration(client, driver, db):
    photo = upload(client, driver["headers"], name="car.png")
    papers = upload(client, driver["headers"], data=JPEG, name="book.jpg")

    response = client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(photo_asset_id=photo["id"], registration_asset_id=papers["id"]),
        headers=driver["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["photo_asset_id"] == photo["id"]
    assert body["registration_asset_id"] == papers["id"]
    assert body["status"] == "PENDING"
    assert body["vehicle_photo_url"] is None

    vehicle = db.get(Vehicle, uuid.UUID(body["id"]))
    assert vehicle.photo_asset_id == uuid.UUID(photo["id"])


def test_vehicle_cannot_reference_someone_elses_upload(client, driver):
    stranger = register(client, email=f"other-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    stolen = upload(client, stranger["headers"])

    response = client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(photo_asset_id=stolen["id"]),
        headers=driver["headers"],
    )
    assert response.status_code == 404


def test_verification_upload_cannot_be_reused_as_a_vehicle_document(client, driver):
    verification_asset = upload(client, driver["headers"], endpoint="/uploads/verification")
    response = client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(registration_asset_id=verification_asset["id"]),
        headers=driver["headers"],
    )
    # right owner, wrong purpose — refused with a readable reason
    assert response.status_code == 422
    assert "upload" in response.json()["error"]["message"].lower()


def test_owner_can_replace_the_vehicle_photo_upload(client, driver):
    first = upload(client, driver["headers"])
    vehicle = client.post(
        "/api/v1/vehicles", json=vehicle_payload(photo_asset_id=first["id"]), headers=driver["headers"]
    ).json()

    second = upload(client, driver["headers"], data=JPEG, name="car2.jpg")
    patched = client.patch(
        f"/api/v1/vehicles/{vehicle['id']}",
        json={"photo_asset_id": second["id"]},
        headers=driver["headers"],
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["photo_asset_id"] == second["id"]


def test_admin_vehicle_queue_exposes_both_documents(client, driver, admin, db):
    photo = upload(client, driver["headers"])
    papers = upload(client, driver["headers"], data=JPEG, name="book.jpg")
    client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(photo_asset_id=photo["id"], registration_asset_id=papers["id"]),
        headers=driver["headers"],
    )

    queue = client.get("/api/v1/admin/vehicles", headers=admin["headers"]).json()
    row = next(item for item in queue["items"] if item["owner_id"] == driver["user_id"])
    assert row["photo_asset_id"] == photo["id"]
    assert row["registration_asset_id"] == papers["id"]

    # and the administrator can actually open them
    assert client.get(f"/api/v1/media/{papers['id']}", headers=admin["headers"]).status_code == 200


# ----------------------------------------------------------------- the sweep
def test_sweep_deletes_only_unreferenced_files_after_the_window(client, driver, db):
    referenced = upload(client, driver["headers"], name="kept.png")
    client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(photo_asset_id=referenced["id"]),
        headers=driver["headers"],
    )
    orphan = upload(client, driver["headers"], name="orphan.png")

    backdate(db, referenced["id"], days=30)
    backdate(db, orphan["id"], days=30)

    result = media_service.sweep_orphans(db, older_than_days=7)
    assert result.deleted == 1
    assert result.kept_referenced == 1
    assert result.bytes_reclaimed == orphan["byte_size"]

    db.expire_all()
    assert db.get(MediaAsset, uuid.UUID(referenced["id"])) is not None
    assert db.get(MediaAsset, uuid.UUID(orphan["id"])) is None
    # the file is gone from disk too, not just the row
    assert client.get(f"/api/v1/media/{orphan['id']}", headers=driver["headers"]).status_code == 404


def test_sweep_keeps_a_fresh_orphan_inside_the_retention_window(client, driver, db):
    fresh = upload(client, driver["headers"], name="fresh.png")
    result = media_service.sweep_orphans(db, older_than_days=7)
    assert result.deleted == 0
    assert result.kept_too_new == 1
    assert db.get(MediaAsset, uuid.UUID(fresh["id"])) is not None


def test_dry_run_reports_without_deleting(client, driver, db):
    orphan = upload(client, driver["headers"], name="orphan.png")
    backdate(db, orphan["id"], days=30)

    result = media_service.sweep_orphans(db, older_than_days=7, dry_run=True)
    assert result.deleted == 1
    assert result.dry_run is True
    assert db.get(MediaAsset, uuid.UUID(orphan["id"])) is not None
    assert client.get(f"/api/v1/media/{orphan['id']}", headers=driver["headers"]).status_code == 200


def test_verification_document_is_referenced_too(client, db):
    # a member without a university address still has to be verified by an admin
    member = register(client, email=f"manual-{uuid.uuid4().hex[:6]}@gmail.com")
    asset = upload(client, member["headers"], endpoint="/uploads/verification")
    submitted = client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID", "document_asset_id": asset["id"]},
        headers=member["headers"],
    )
    assert submitted.status_code == 201, submitted.text
    backdate(db, asset["id"], days=30)

    result = media_service.sweep_orphans(db, older_than_days=7)
    assert result.deleted == 0
    assert result.kept_referenced == 1


def test_housekeeping_run_reports_the_sweep(client, driver, db):
    from app.services.maintenance_service import run_all

    orphan = upload(client, driver["headers"], name="old.png")
    backdate(db, orphan["id"], days=30)

    result = run_all(db, media_retention_days=7)
    assert result.orphaned_media == 1
    assert result.as_dict()["orphaned_media"] == 1


def test_storage_stats_count_files_bytes_and_orphans(client, driver, db):
    kept = upload(client, driver["headers"], name="kept.png")
    client.post(
        "/api/v1/vehicles",
        json=vehicle_payload(registration_asset_id=kept["id"]),
        headers=driver["headers"],
    )
    upload(client, driver["headers"], name="orphan.png")

    stats = media_service.storage_stats(db)
    assert stats.files == 2
    assert stats.bytes == kept["byte_size"] * 2
    assert stats.orphans == 1
    assert stats.orphan_bytes == kept["byte_size"]


def test_admin_media_endpoint_reports_storage(client, driver, admin):
    upload(client, driver["headers"], name="orphan.png")
    body = client.get("/api/v1/admin/media", headers=admin["headers"]).json()

    assert body["files"] == 1
    assert body["orphans"] == 1
    assert body["retention_days"] == settings.MEDIA_ORPHAN_RETENTION_DAYS
    assert body["max_upload_bytes"] == settings.MAX_UPLOAD_BYTES
    assert body["oldest"] is not None


def test_non_admin_cannot_read_media_stats(client, driver):
    assert client.get("/api/v1/admin/media", headers=driver["headers"]).status_code == 403


def test_sweep_cli_dry_run_then_real_run(client, driver, db, capsys):
    from scripts import sweep_media

    asset = upload(client, driver["headers"], name="orphan.png")

    # inside the retention window: nothing is deleted either way
    assert sweep_media.main(["--dry-run"]) == 0
    assert "orphans deleted=0" in capsys.readouterr().out

    backdate(db, asset["id"], days=30)
    assert sweep_media.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[dry-run] orphans deleted=1" in out

    assert sweep_media.main([]) == 0
    assert "orphans deleted=1" in capsys.readouterr().out

    assert sweep_media.main(["--stats"]) == 0
    stats_out = capsys.readouterr().out
    assert "files=0" in stats_out
    assert "retention=" in stats_out
