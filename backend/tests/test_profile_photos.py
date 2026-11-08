"""Profile photos (§5, §4, Phase 13).

The point of this feature is that a face is *semi-public* — every signed-in member may
see it — while an ID card stays private. The tests therefore check the visibility
boundary as carefully as the upload itself: an avatar must be readable by other
members, and unreadable by anonymous callers; the replaced file must be gone from
disk; and the housekeeping sweep must never treat a referenced avatar as an orphan.
"""

from __future__ import annotations

import base64
import io
import uuid

import pytest

from PIL import Image

from app.core.config import settings
from app.models.media import PURPOSE_PROFILE_PHOTO, MediaAsset
from app.models.user import User
from app.services import media_service
from tests.helpers import auth_header, register

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BAAAAD"
    "AAGEAAG0j0m0AAAAASUVORK5CYII="
)
# A real (tiny) JPEG. Since Phase 14 the server decodes the picture, so a fake header
# with no image behind it is refused — see test_a_truncated_image_is_refused_*.
def _real_jpeg(size: int = 24) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), (30, 90, 140)).save(buffer, "JPEG")
    return buffer.getvalue()


JPEG = _real_jpeg()
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>\n%%EOF\n"
NOT_AN_IMAGE = b"#!/bin/sh\necho pwned\n"


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(root), raising=False)
    return root


@pytest.fixture
def member(client):
    body = register(client, email=f"photo-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user": body["user"]}


@pytest.fixture
def other_member(client):
    body = register(client, email=f"viewer-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user": body["user"]}


def upload(client, headers, *, data=PNG_1PX, name="me.png", content_type="image/png"):
    return client.post(
        "/api/v1/users/me/photo", headers=headers, files={"file": (name, data, content_type)}
    )


# ------------------------------------------------------------------ happy path
def test_upload_sets_a_readable_photo(client, member, db):
    response = upload(client, member["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    url = body["profile_photo_url"]
    assert url.startswith(f"/api/v1/users/{member['user']['id']}/photo?v=")

    read = client.get(url, headers=member["headers"])
    assert read.status_code == 200
    # Phase 14: the stored file is a normalised 512 px WebP, not the uploaded bytes.
    assert read.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(read.content)).size == (settings.PROFILE_PHOTO_MAX_DIMENSION,) * 2
    assert read.headers["x-content-type-options"] == "nosniff"
    assert "private" in read.headers["cache-control"]
    assert read.headers["etag"]

    row = db.get(User, uuid.UUID(member["user"]["id"]))
    assert row.profile_photo_asset_id is not None
    asset = db.get(MediaAsset, row.profile_photo_asset_id)
    assert asset.purpose == PURPOSE_PROFILE_PHOTO
    assert asset.owner_id == row.id


def test_another_member_can_read_a_profile_photo(client, member, other_member):
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    response = client.get(url, headers=other_member["headers"])
    assert response.status_code == 200, "a face is visible to the community"
    owner_view = client.get(url, headers=member["headers"])
    assert response.content == owner_view.content, "everybody sees the same stored picture"


def test_anonymous_readers_are_refused(client, member):
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    assert client.get(url).status_code == 401


def test_the_photo_appears_in_public_and_admin_payloads(client, member, other_member, admin):
    url = upload(client, member["headers"]).json()["profile_photo_url"]

    public = client.get(f"/api/v1/users/{member['user']['id']}/public", headers=other_member["headers"])
    assert public.status_code == 200
    assert public.json()["profile_photo_url"] == url

    me = client.get("/api/v1/users/me", headers=member["headers"])
    assert me.json()["profile_photo_url"] == url

    listed = client.get(
        "/api/v1/admin/users", headers=admin["headers"], params={"search": member["user"]["email"]}
    )
    assert listed.status_code == 200
    rows = listed.json()["items"]
    assert len(rows) == 1, "the search is by email, so exactly one member matches"
    assert rows[0]["profile_photo_url"] == url


# ------------------------------------------------------------- replacing a photo
def test_replacing_a_photo_deletes_the_previous_file(client, member, db):
    first_url = upload(client, member["headers"]).json()["profile_photo_url"]
    first_asset_id = first_url.rsplit("v=", 1)[1]
    assert db.get(MediaAsset, uuid.UUID(first_asset_id)).blob, "the bytes are stored in the database"

    second = upload(client, member["headers"], data=JPEG, name="new.jpg", content_type="image/jpeg")
    assert second.status_code == 201
    second_url = second.json()["profile_photo_url"]
    assert second_url != first_url, "the URL is the cache key, so it must change"

    db.expire_all()
    assert db.get(MediaAsset, uuid.UUID(first_asset_id)) is None
    # The row (and its bytes in `blob`) is gone with it, so the replaced face does not linger.
    second_stored = client.get(second_url, headers=member["headers"])
    assert Image.open(io.BytesIO(second_stored.content)).format == "WEBP"


def test_uploading_a_photo_supersedes_a_legacy_external_link(client, member, db):
    patched = client.patch(
        "/api/v1/users/me", headers=member["headers"],
        json={"profile_photo_url": "https://example.com/old-avatar.png"},
    )
    assert patched.status_code == 200
    assert patched.json()["profile_photo_url"] == "https://example.com/old-avatar.png"

    upload(client, member["headers"])
    db.expire_all()
    row = db.get(User, uuid.UUID(member["user"]["id"]))
    assert row.profile_photo_url is None, "the uploaded picture wins"
    assert client.get("/api/v1/users/me", headers=member["headers"]).json()["profile_photo_url"].startswith(
        "/api/v1/users/"
    )


# ------------------------------------------------------------------- deleting
def test_delete_removes_the_row_and_the_file(client, member, db, media_root):
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    asset_id = uuid.UUID(url.rsplit("v=", 1)[1])
    path = media_service.absolute_path(db.get(MediaAsset, asset_id))

    response = client.delete("/api/v1/users/me/photo", headers=member["headers"])
    assert response.status_code == 200
    assert response.json()["profile_photo_url"] is None

    db.expire_all()
    assert db.get(MediaAsset, asset_id) is None
    assert not path.exists()
    assert client.get(f"/api/v1/users/{member['user']['id']}/photo", headers=member["headers"]).status_code == 404


def test_deleting_when_there_is_no_photo_is_harmless(client, member):
    response = client.delete("/api/v1/users/me/photo", headers=member["headers"])
    assert response.status_code == 200
    assert response.json()["profile_photo_url"] is None


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    ("data", "name", "content_type", "status"),
    [
        (PDF, "cv.pdf", "application/pdf", 422),          # a document is not a face
        (NOT_AN_IMAGE, "photo.png", "image/png", 422),    # extension and header lie
        (b"", "empty.png", "image/png", 422),             # nothing at all
    ],
)
def test_bad_uploads_are_refused(client, member, data, name, content_type, status, db):
    response = upload(client, member["headers"], data=data, name=name, content_type=content_type)
    assert response.status_code == status
    db.expire_all()
    assert db.scalar(
        __import__("sqlalchemy").select(MediaAsset).where(MediaAsset.purpose == PURPOSE_PROFILE_PHOTO)
    ) is None


def test_a_file_over_the_photo_limit_is_refused(client, member):
    oversized = PNG_1PX + b"\x00" * settings.MAX_PROFILE_PHOTO_BYTES
    response = upload(client, member["headers"], data=oversized)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_the_photo_limit_is_lower_than_the_document_limit(client, member):
    # 3 MB is a legal document but not a legal avatar — proof the two caps are distinct.
    assert settings.MAX_PROFILE_PHOTO_BYTES < settings.MAX_UPLOAD_BYTES
    payload = PNG_1PX + b"\x00" * (3 * 1024 * 1024)
    assert upload(client, member["headers"], data=payload).status_code == 413


def test_a_declared_document_type_is_refused_even_with_image_bytes(client, member):
    """A client that *declares* PDF is refused: the declared type must be an image too."""
    response = upload(
        client, member["headers"], data=PNG_1PX, name="me.png", content_type="application/pdf"
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["declared"] == "application/pdf"


# ------------------------------------------------- where the photo must appear
def test_a_drivers_photo_reaches_the_explore_payload(client, member, other_member):
    """A ride card is where a face matters most — the payload must carry it."""
    url = upload(client, member["headers"]).json()["profile_photo_url"]

    vehicle = client.post(
        "/api/v1/vehicles",
        headers=member["headers"],
        json={
            "vehicle_type": "CAR",
            "make_and_model": "Suzuki Cultus",
            "color": "White",
            "registration_number": f"ABC-{uuid.uuid4().int % 9999}",
            "passenger_capacity": 1,
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    ride = client.post(
        "/api/v1/rides",
        headers=member["headers"],
        json={
            "vehicle_id": vehicle.json()["id"],
            "direction": "HOME_TO_UNIVERSITY",
            "pickup_area": "Gulshan",
            "pickup_point": {"latitude": 24.9205, "longitude": 67.0971},
            "departure_at": (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                + __import__("datetime").timedelta(days=1)
            ).isoformat(),
            "available_seats": 1,
            "fuel_preference": "FREE",
            "contribution_type": "NONE",
        },
    )
    assert ride.status_code == 201, ride.text

    explore = client.get("/api/v1/rides?limit=20", headers=other_member["headers"])
    assert explore.status_code == 200
    mine = [item for item in explore.json()["items"] if item["driver"]["id"] == member["user"]["id"]]
    assert mine, "the published ride should be in Explore"
    assert mine[0]["driver"]["profile_photo_url"] == url


# ------------------------------------------------------------- housekeeping
def test_the_sweep_never_deletes_a_referenced_photo(client, member, db):
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    asset_id = uuid.UUID(url.rsplit("v=", 1)[1])

    result = media_service.sweep_orphans(db, older_than_days=0)
    assert result.deleted == 0
    assert result.kept_referenced == 1
    assert db.get(MediaAsset, asset_id) is not None


def test_the_sweep_still_collects_a_photo_nobody_references(client, member, db, tmp_path):
    """An abandoned upload (picked, never saved) is collected once it is old enough."""
    from datetime import datetime, timedelta, timezone

    upload(client, member["headers"])
    client.delete("/api/v1/users/me/photo", headers=member["headers"])

    stray = MediaAsset(
        owner_id=uuid.UUID(member["user"]["id"]),
        purpose=PURPOSE_PROFILE_PHOTO,
        storage_path="2026/11/abandoned.png",
        content_type="image/png",
        byte_size=len(PNG_1PX),
        checksum_sha256="0" * 64,
        original_filename="abandoned.png",
    )
    stray.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.add(stray)
    db.commit()

    result = media_service.sweep_orphans(db, older_than_days=7)
    assert result.deleted == 1


def test_storage_stats_counts_a_profile_photo_as_referenced(client, member, db):
    upload(client, member["headers"])
    stats = media_service.storage_stats(db)
    assert stats.files == 1
    assert stats.orphans == 0


# ------------------------------------------------------------------- privacy
def test_a_photo_cannot_be_read_through_the_asset_endpoint(client, member, other_member):
    """The asset id in the URL is not a capability: /media/{id} stays owner+admin."""
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    asset_id = url.rsplit("v=", 1)[1]
    assert client.get(f"/api/v1/media/{asset_id}", headers=other_member["headers"]).status_code == 403


def test_owner_can_still_read_their_own_asset(client, member):
    url = upload(client, member["headers"]).json()["profile_photo_url"]
    asset_id = url.rsplit("v=", 1)[1]
    assert client.get(f"/api/v1/media/{asset_id}", headers=member["headers"]).status_code == 200


def test_an_unknown_member_has_no_photo(client, member, other_member):
    unknown = uuid.uuid4()
    response = client.get(f"/api/v1/users/{unknown}/photo", headers=member["headers"])
    assert response.status_code == 404


def test_a_pdf_pretending_to_be_a_photo_is_rejected_even_with_a_png_name(client, member):
    response = upload(client, member["headers"], data=PDF, name="selfie.png", content_type="image/png")
    assert response.status_code == 422
