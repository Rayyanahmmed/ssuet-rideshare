"""Image normalisation for profile photos (§4, §16, Phase 14).

A phone photo is 4–8 MB, 12 megapixels, and carries metadata nobody meant to publish:
GPS coordinates of where the selfie was taken, the device model, sometimes a timestamp.
None of that belongs in an avatar that is served to every member of the community, and
none of it is *needed* — a face reads perfectly at 512 pixels.

So a profile photo is not stored as uploaded. It is:

1. **decoded** — which also proves it really is an image, not a PNG header followed by
   something else;
2. **pixel-budget checked** — a 250 KB PNG can claim 30000×30000 pixels, which is 3.6 GB
   of memory once decoded. Anything above `MAX_PHOTO_PIXELS` is refused before decoding;
3. **auto-oriented** — the EXIF `Orientation` tag is *applied* to the pixels, then the
   metadata is dropped, so a sideways phone photo does not stay sideways;
4. **centre-cropped square and resized** — to `PROFILE_PHOTO_MAX_DIMENSION`;
5. **re-encoded** as WebP. Re-encoding is what strips the metadata: nothing is copied
   from the original container.

Documents (ID cards, registration books) are deliberately **not** processed: an
administrator has to read the text, so those bytes are stored exactly as uploaded.
"""

from __future__ import annotations

import io
import logging
from collections import OrderedDict

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.core.exceptions import ValidationAppError

logger = logging.getLogger("ssuet.rideshare.images")

# Pillow's own bomb guard. Kept in step with our setting so `Image.open` refuses before
# the decoder allocates the pixel buffer.
Image.MAX_IMAGE_PIXELS = max(settings.MAX_PHOTO_PIXELS, Image.MAX_IMAGE_PIXELS or 0)

WEBP_MIME = "image/webp"
WEBP_EXT = "webp"

# Small, bounded cache of derived thumbnails: keyed by (sha256, dimension). A member list
# asks for the same handful of faces over and over; 256 entries is a few megabytes.
_THUMB_CACHE: OrderedDict[tuple[str, int], bytes] = OrderedDict()
_THUMB_CACHE_MAX = 256


class PhotoTooLargeError(ValidationAppError):
    """The image is within the byte limit but far too big once decoded."""

    status_code = 422
    code = "PHOTO_TOO_LARGE"


def _decode(data: bytes) -> Image.Image:
    """Decode bytes into an RGB image, refusing anything Pillow cannot read."""
    try:
        image = Image.open(io.BytesIO(data))
        # `load()` forces the decode here, so a truncated file fails at upload time
        # rather than being discovered by whoever opens the profile later.
        image.load()
    except Image.DecompressionBombError as exc:  # pragma: no cover - Pillow's own guard
        raise PhotoTooLargeError(
            "This photo is too large to process. Try a smaller picture."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationAppError(
            "This file could not be read as an image. Try another photo."
        ) from None
    return image


def _square_thumbnail(image: Image.Image, dimension: int) -> Image.Image:
    """Centre-crop to a square, then resize — never stretch a face out of shape."""
    return ImageOps.fit(
        image,
        (dimension, dimension),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.4),  # a little above centre: faces usually sit high
    )


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="WEBP",
        quality=settings.PROFILE_PHOTO_WEBP_QUALITY,
        method=4,  # the slow-ish encoder: better quality per byte, still ~10 ms
    )
    return buffer.getvalue()


def normalise_profile_photo(data: bytes) -> bytes:
    """Return the WebP bytes that will actually be stored for a profile photo."""
    image = _decode(data)

    pixels = image.width * image.height
    if pixels > settings.MAX_PHOTO_PIXELS:
        raise PhotoTooLargeError(
            f"This photo is {image.width}×{image.height} pixels. "
            f"The limit is {settings.MAX_PHOTO_PIXELS // 1_000_000} megapixels."
        )

    # Orientation is applied to the pixels *before* the metadata is discarded.
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    square = _square_thumbnail(image, settings.PROFILE_PHOTO_MAX_DIMENSION)
    encoded = _encode(square)
    logger.info(
        "Normalised profile photo %dx%d (%d bytes) → %dx%d WebP (%d bytes)",
        image.width,
        image.height,
        len(data),
        square.width,
        square.height,
        len(encoded),
    )
    return encoded


def thumbnail(data: bytes, dimension: int | None = None) -> bytes:
    """Downscale an already-normalised photo for list views.

    Derived on demand rather than stored: the source is at most 512×512, so the resize
    costs a couple of milliseconds, and the result is cached in-process *and* on the
    client (the URL is versioned by the asset id).
    """
    size = dimension or settings.PROFILE_PHOTO_THUMB_DIMENSION
    image = Image.open(io.BytesIO(data))
    image.load()
    return _encode(_square_thumbnail(image, size))


def cached_thumbnail(checksum: str, data: bytes, dimension: int | None = None) -> bytes:
    """`thumbnail()` behind a small LRU; `checksum` identifies the source bytes."""
    size = dimension or settings.PROFILE_PHOTO_THUMB_DIMENSION
    key = (checksum, size)
    hit = _THUMB_CACHE.get(key)
    if hit is not None:
        _THUMB_CACHE.move_to_end(key)
        return hit
    encoded = thumbnail(data, size)
    _THUMB_CACHE[key] = encoded
    if len(_THUMB_CACHE) > _THUMB_CACHE_MAX:
        _THUMB_CACHE.popitem(last=False)
    return encoded


def clear_thumbnail_cache() -> None:
    """Used by tests; a long-lived process never needs this."""
    _THUMB_CACHE.clear()
