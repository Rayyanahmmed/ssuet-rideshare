"""Profile photo normalisation (§4, §16, Phase 14).

A phone photo is not an avatar. These tests pin down what the server must do to the
bytes before anybody else can fetch them: drop the metadata (GPS included), respect the
orientation the camera recorded, crop and resize to a sane size, refuse a decompression
bomb without decoding it, and leave documents untouched — an administrator still has to
be able to read an ID card.
"""

from __future__ import annotations

import base64
import io
import os
import uuid

import pytest
from PIL import Image, ImageDraw

from app.core.config import settings
from app.services import image_service, media_service
from tests.helpers import register


def make_photo(size=(1200, 1600), *, exif_orientation: int | None = None, with_gps: bool = False,
               noise: int | None = None, fmt: str = "JPEG", **save_kwargs) -> bytes:
    """A deterministic stand-in for a phone photo."""
    if noise is not None:
        image = Image.effect_noise(size, noise).convert("RGB")
    else:
        image = Image.new("RGB", size, (210, 225, 235))
        draw = ImageDraw.Draw(image)
        draw.ellipse((size[0] * 0.25, size[1] * 0.15, size[0] * 0.75, size[1] * 0.75), fill=(240, 225, 200))
    exif = None
    if exif_orientation is not None or with_gps:
        exif = image.getexif()
        if exif_orientation is not None:
            exif[0x0112] = exif_orientation
        exif[0x010F] = "SSUET Test Phone"
        if with_gps:
            gps = exif.get_ifd(0x8825)
            gps[1] = "N"
            gps[2] = (24.0, 51.0, 0.0)
            gps[3] = "E"
            gps[4] = (67.0, 3.0, 0.0)
    buffer = io.BytesIO()
    options = dict(save_kwargs)
    if exif is not None:  # Pillow raises on an explicit exif=None
        options["exif"] = exif
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(root), raising=False)
    image_service.clear_thumbnail_cache()
    return root


@pytest.fixture
def member(client):
    body = register(client, email=f"pixels-{uuid.uuid4().hex[:6]}@ssuet.edu.pk")
    return {"headers": body["headers"], "user": body["user"]}


def upload(client, headers, data, name="photo.jpg", content_type="image/jpeg"):
    return client.post("/api/v1/users/me/photo", headers=headers, files={"file": (name, data, content_type)})


# ------------------------------------------------------------------ the promise
def test_a_big_photo_is_stored_small_and_square(client, member):
    response = upload(client, member["headers"], make_photo((1200, 1600)))
    assert response.status_code == 201, response.text

    stored = client.get(response.json()["profile_photo_url"], headers=member["headers"])
    image = Image.open(io.BytesIO(stored.content))
    assert image.format == "WEBP"
    assert image.size == (settings.PROFILE_PHOTO_MAX_DIMENSION,) * 2
    assert stored.headers["content-type"] == "image/webp"


def test_metadata_including_gps_is_stripped(client, member):
    source = make_photo((900, 900), exif_orientation=1, with_gps=True)
    assert "GPSInfo" in Image.open(io.BytesIO(source)).getexif() or Image.open(io.BytesIO(source)).getexif().get_ifd(0x8825)

    response = upload(client, member["headers"], source)
    assert response.status_code == 201
    stored = client.get(response.json()["profile_photo_url"], headers=member["headers"])
    exif = Image.open(io.BytesIO(stored.content)).getexif()
    assert not exif, f"the stored file must carry no metadata, found {dict(exif)}"
    assert not exif.get_ifd(0x8825)


def test_the_orientation_the_camera_recorded_is_applied(tmp_path):
    """Orientation 6 = "rotate 90° clockwise"; the pixels must actually be rotated."""
    image = Image.new("RGB", (400, 200), (200, 200, 200))
    ImageDraw.Draw(image).rectangle((0, 0, 100, 100), fill=(255, 0, 0))  # red in the top-left
    exif = image.getexif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)

    normalised = image_service.normalise_profile_photo(buffer.getvalue())
    result = Image.open(io.BytesIO(normalised)).convert("RGB")

    # After a 90° clockwise rotation the top-left corner is where the bottom-left was.
    assert result.size[0] == result.size[1]
    top_right = result.getpixel((result.size[0] - 5, 5))
    assert top_right[0] > 150 and top_right[1] < 100, f"expected red at the top-right, got {top_right}"


def test_a_portrait_photo_is_centre_cropped_not_squashed(tmp_path):
    """A wide photo and a tall photo must both come out square without distortion."""
    wide = make_photo((1600, 400))
    tall = make_photo((400, 1600))
    for payload in (wide, tall):
        out = Image.open(io.BytesIO(image_service.normalise_profile_photo(payload)))
        assert out.size == (settings.PROFILE_PHOTO_MAX_DIMENSION,) * 2


# --------------------------------------------------------------- the refusals
def test_a_decompression_bomb_is_refused_without_being_decoded():
    """A tiny file that claims 30000×30000 pixels: 3.6 GB if we were naive."""
    buffer = io.BytesIO()
    Image.new("L", (10, 10)).save(buffer, "PNG")
    payload = bytearray(buffer.getvalue())
    # Patch the IHDR width/height to 30000×30000 and fix the CRC by re-saving the header.
    payload[16:20] = (30000).to_bytes(4, "big")
    payload[20:24] = (30000).to_bytes(4, "big")
    import zlib

    payload[29:33] = (zlib.crc32(bytes(payload[12:29])) & 0xFFFFFFFF).to_bytes(4, "big")

    with pytest.raises(image_service.PhotoTooLargeError) as excinfo:
        image_service.normalise_profile_photo(bytes(payload))
    assert excinfo.value.status_code == 422


def test_a_bomb_is_refused_through_the_api(client, member):
    buffer = io.BytesIO()
    Image.new("L", (10, 10)).save(buffer, "PNG")
    payload = bytearray(buffer.getvalue())
    payload[16:20] = (30000).to_bytes(4, "big")
    payload[20:24] = (30000).to_bytes(4, "big")
    import zlib

    payload[29:33] = (zlib.crc32(bytes(payload[12:29])) & 0xFFFFFFFF).to_bytes(4, "big")

    response = upload(client, member["headers"], bytes(payload), name="bomb.png", content_type="image/png")
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"PHOTO_TOO_LARGE", "VALIDATION_ERROR"}


def test_a_truncated_image_is_refused_and_nothing_is_stored(client, member, db, media_root):
    broken = make_photo((600, 600))[:400]  # valid JPEG magic, incomplete file
    response = upload(client, member["headers"], broken)
    assert response.status_code == 422
    assert list(media_root.rglob("*.webp")) == []
    from app.models.media import MediaAsset
    from sqlalchemy import select

    assert db.scalars(select(MediaAsset)).all() == []


def test_a_png_named_jpeg_still_becomes_webp(client, member):
    response = upload(client, member["headers"], make_photo((700, 700), fmt="PNG"), name="selfie.png", content_type="image/png")
    assert response.status_code == 201
    stored = client.get(response.json()["profile_photo_url"], headers=member["headers"])
    assert Image.open(io.BytesIO(stored.content)).format == "WEBP"


# ---------------------------------------------------------------- thumbnails
def test_the_thumbnail_variant_is_smaller_and_has_its_own_etag(client, member):
    url = upload(client, member["headers"], make_photo((1200, 1200), noise=40)).json()["profile_photo_url"]

    full = client.get(url, headers=member["headers"])
    thumb = client.get(url + "&size=thumb", headers=member["headers"])

    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(thumb.content)).size == (settings.PROFILE_PHOTO_THUMB_DIMENSION,) * 2
    assert len(thumb.content) < len(full.content)
    assert thumb.headers["etag"] != full.headers["etag"]
    assert thumb.headers["etag"].startswith('"thumb-')


def test_the_thumbnail_is_cached_in_process(client, member, monkeypatch):
    url = upload(client, member["headers"], make_photo((1000, 1000), noise=40)).json()["profile_photo_url"]
    first = client.get(url + "&size=thumb", headers=member["headers"]).content

    calls = {"n": 0}
    original = image_service.thumbnail

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(image_service, "thumbnail", counting)
    second = client.get(url + "&size=thumb", headers=member["headers"]).content
    assert second == first
    assert calls["n"] == 0, "the second request must be served from the cache"


def test_the_variant_parameter_is_validated(client, member):
    url = upload(client, member["headers"], make_photo((600, 600))).json()["profile_photo_url"]
    assert client.get(url + "&size=huge", headers=member["headers"]).status_code == 422


# -------------------------------------------------------------- what must not change
def test_a_document_is_stored_byte_for_byte(client, member, db):
    """An ID card must stay legible: no resizing, no re-encoding, no metadata loss."""
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>\n%%EOF\n"
    response = client.post(
        "/api/v1/uploads/verification",
        headers=member["headers"],
        files={"file": ("student-id.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["byte_size"] == len(pdf)
    stored = client.get(f"/api/v1/media/{response.json()['id']}", headers=member["headers"])
    assert stored.content == pdf


def test_an_oversized_upload_is_still_refused_before_processing(client, member, monkeypatch):
    """The 2 MB ceiling applies to what was uploaded, not to the cleaned result."""
    monkeypatch.setattr(settings, "MAX_PROFILE_PHOTO_BYTES", 200 * 1024, raising=False)
    payload = make_photo((1500, 1500), noise=60)  # noisy → well over 200 KB
    assert len(payload) > 200 * 1024
    response = upload(client, member["headers"], payload)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_replacing_a_photo_removes_the_previous_webp(client, member, db):
    from sqlalchemy import select

    from app.models.media import MediaAsset

    first = upload(client, member["headers"], make_photo((800, 800))).json()["profile_photo_url"]
    assert db.get(MediaAsset, uuid.UUID(first.rsplit("v=", 1)[1])).blob

    upload(client, member["headers"], make_photo((900, 900), noise=20))
    db.expire_all()
    stored = db.scalars(select(MediaAsset)).all()
    assert len(stored) == 1
    assert stored[0].content_type == "image/webp"
