"""Media upload pipeline (§4, §16, Phase 9).

Covers the security properties that matter for a student ID card: content (not
extension) validation, a hard size cap, storage paths that cannot be influenced by
the client, and reads that are authorised per request rather than served from a
public directory.
"""

from __future__ import annotations

import base64
import uuid

import pytest

from app.core.config import settings
from app.models.media import MediaAsset
from tests.helpers import auth_header, register

# 1×1 transparent PNG — the smallest real image, so `sniff()` sees genuine magic bytes.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AABAAA//8D"
    "AAGEAAG0j0m0AAAAAElFTkSuQmCC"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>\n%%EOF\n"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
NOT_AN_IMAGE = b"#!/bin/sh\necho pwned\n"


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    """Every test writes into its own directory; nothing leaks into the repo."""
    root = tmp_path / "media"
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(root), raising=False)
    return root


@pytest.fixture
def uploader(client):
    body = register(client, email=f"uploader-{uuid.uuid4().hex[:6]}@gmail.com")
    return {"headers": body["headers"], "user_id": body["user"]["id"]}


def upload(client, headers, *, data=PNG_1PX, name="id-card.png", content_type="image/png"):
    return client.post(
        "/api/v1/uploads/verification",
        files={"file": (name, data, content_type)},
        headers=headers,
    )


# ----------------------------------------------------------------- happy paths
def test_student_uploads_a_png_and_gets_an_opaque_reference(client, uploader, media_root, db):
    response = upload(client, uploader["headers"])
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["content_type"] == "image/png"
    assert body["byte_size"] == len(PNG_1PX)
    assert body["purpose"] == "VERIFICATION_DOCUMENT"
    assert len(body["checksum_sha256"]) == 64
    assert body["url"] == f"/api/v1/media/{body['id']}"

    asset = db.get(MediaAsset, uuid.UUID(body["id"]))
    assert asset is not None
    # Stored path is generated, dated and relative — the client never chooses it.
    assert asset.storage_path.startswith("uploads/")
    assert asset.storage_path.endswith(".png")
    assert str(uuid.UUID(asset.storage_path.rsplit("/", 1)[-1].split(".")[0]))
    assert asset.blob and len(asset.blob) == asset.byte_size, "the bytes are stored in the database"
    assert not any(media_root.rglob("*.png")), "nothing is written to local disk"


@pytest.mark.parametrize(
    ("data", "name", "declared", "expected"),
    [
        (JPEG, "card.jpg", "image/jpeg", "image/jpeg"),
        (PDF, "fee-receipt.pdf", "application/pdf", "application/pdf"),
        (WEBP, "card.webp", "image/webp", "image/webp"),
        # A renamed image is accepted and stored by its *real* type, not its name.
        (PNG_1PX, "card.jpg", "image/jpeg", "image/png"),
    ],
)
def test_accepted_types_are_decided_by_content(client, uploader, data, name, declared, expected):
    response = upload(client, uploader["headers"], data=data, name=name, content_type=declared)
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == expected


def test_client_filename_cannot_escape_the_media_root(client, uploader, media_root, db):
    response = upload(
        client, uploader["headers"], name="../../../etc/passwd.png", content_type="image/png"
    )
    assert response.status_code == 201, response.text
    asset = db.get(MediaAsset, uuid.UUID(response.json()["id"]))
    assert ".." not in asset.storage_path
    assert asset.blob is not None


def test_original_filename_is_sanitised_for_display(client, uploader):
    response = upload(client, uploader["headers"], name="my card (front)!.png")
    assert response.status_code == 201, response.text
    assert response.json()["original_filename"] == "my_card_front_.png"


# --------------------------------------------------------------- rejections
def test_executable_content_is_rejected_even_when_named_jpg(client, uploader):
    response = upload(client, uploader["headers"], data=NOT_AN_IMAGE, name="card.jpg")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_file_is_rejected(client, uploader):
    response = upload(client, uploader["headers"], data=b"", name="empty.png")
    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()


def test_oversize_upload_is_refused_and_leaves_no_partial_file(client, uploader, media_root, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 2048, raising=False)
    response = upload(client, uploader["headers"], data=PNG_1PX + b"\x00" * 8192)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    leftovers = [p for p in media_root.rglob("*") if p.is_file()]
    assert leftovers == []


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/v1/uploads/verification",
        files={"file": ("id.png", PNG_1PX, "image/png")},
    )
    assert response.status_code == 401


def test_upload_requires_a_file_part(client, uploader):
    response = client.post("/api/v1/uploads/verification", headers=uploader["headers"])
    assert response.status_code == 422


# ------------------------------------------------------------------- reading
def test_owner_reads_own_document_with_hardened_headers(client, uploader):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    response = client.get(f"/api/v1/media/{asset_id}", headers=uploader["headers"])

    assert response.status_code == 200
    assert response.content == PNG_1PX
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert "inline" in response.headers["content-disposition"]


def test_another_student_cannot_read_the_document(client, uploader):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    other = register(client, email=f"nosy-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")

    response = client.get(f"/api/v1/media/{asset_id}", headers=other["headers"])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_administrator_can_read_any_document_for_review(client, uploader, admin):
    asset_id = upload(client, uploader["headers"]).json()["id"]

    response = client.get(f"/api/v1/media/{asset_id}", headers=admin["headers"])
    assert response.status_code == 200
    assert response.content == PNG_1PX


def test_admin_queue_exposes_the_upload_for_review(client, uploader, admin):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID", "document_asset_id": asset_id},
        headers=uploader["headers"],
    )

    queue = client.get("/api/v1/admin/verifications", headers=admin["headers"]).json()
    row = next(item for item in queue["items"] if item["user_id"] == uploader["user_id"])
    assert row["document_asset_id"] == asset_id
    assert row["document_url"] is None


def test_unknown_media_id_is_404(client, uploader):
    response = client.get(f"/api/v1/media/{uuid.uuid4()}", headers=uploader["headers"])
    assert response.status_code == 404


def test_unauthenticated_read_is_401(client, uploader):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    assert client.get(f"/api/v1/media/{asset_id}").status_code == 401


# ------------------------------------------------------------------ deleting
def test_owner_deletes_upload_and_the_file_disappears(client, uploader, media_root, db):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    asset = db.get(MediaAsset, uuid.UUID(asset_id))
    assert client.delete(f"/api/v1/media/{asset_id}", headers=uploader["headers"]).status_code == 204
    db.expire_all()  # the delete happened in the request's session
    assert db.get(MediaAsset, uuid.UUID(asset_id)) is None, "the row and its bytes are gone"
    assert db.get(MediaAsset, uuid.UUID(asset_id)) is None
    assert client.get(f"/api/v1/media/{asset_id}", headers=uploader["headers"]).status_code == 404


def test_another_student_cannot_delete_the_document(client, uploader):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    other = register(client, email=f"deleter-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    assert client.delete(f"/api/v1/media/{asset_id}", headers=other["headers"]).status_code == 403


# ------------------------------------------- verification submission contract
def test_verification_can_reference_an_upload(client, uploader, db):
    asset_id = upload(client, uploader["headers"]).json()["id"]

    response = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "submitted_value": "SSUET-2026-123",
            "document_asset_id": asset_id,
            "note": "Uploaded from the app",
        },
        headers=uploader["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_asset_id"] == asset_id
    assert body["document_url"] is None
    assert body["status"] == "PENDING"


def test_verification_cannot_reference_someone_elses_upload(client, uploader):
    asset_id = upload(client, uploader["headers"]).json()["id"]
    victim_of_attempt = register(client, email=f"claimer-{uuid.uuid4().hex[:6]}@gmail.com")

    response = client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID", "document_asset_id": asset_id},
        headers=victim_of_attempt["headers"],
    )
    # 404, not 403: the endpoint must not reveal that the asset exists
    assert response.status_code == 404


def test_verification_needs_exactly_one_document_source(client, uploader):
    both = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "document_asset_id": str(uuid.uuid4()),
            "document_url": "https://cdn.example.test/id.jpg",
        },
        headers=uploader["headers"],
    )
    assert both.status_code == 422

    neither = client.post(
        "/api/v1/users/me/verification",
        json={"verification_type": "STUDENT_ID"},
        headers=uploader["headers"],
    )
    assert neither.status_code == 422


def test_external_link_submission_still_works(client):
    """The legacy path stays available for members who keep their card in Drive."""
    body = register(client, email=f"link-{uuid.uuid4().hex[:6]}@gmail.com")
    response = client.post(
        "/api/v1/users/me/verification",
        json={
            "verification_type": "STUDENT_ID",
            "document_url": "https://cdn.ssuet-rideshare.test/ids/777.jpg",
        },
        headers=auth_header(body["access_token"]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["document_asset_id"] is None
    assert response.json()["document_url"].startswith("https://cdn.ssuet-rideshare.test/")
