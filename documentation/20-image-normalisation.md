# 20 · Phase 14 — image normalisation

**Status:** complete. A profile photo is no longer stored as uploaded. It is decoded,
oriented, cropped, resized to 512 px and re-encoded — which makes it 50–80× smaller and
removes the metadata (GPS included) that nobody meant to publish.

```
backend$  python -m pytest tests/test_profile_photo_processing.py   # 14 passed (401 total, 94 %)
live:     0.79 MB / 12 MP / GPS-tagged  →  14.8 KB WebP 512×512  (53× smaller, EXIF gone)
```

---

## 1. Why this was worth a phase

Phase 13 shipped avatars. Two problems came with them, both of which only bite in real
use:

1. **Privacy.** A phone photo carries EXIF: GPS coordinates of where it was taken, the
   device model, sometimes a timestamp. The avatar is served to *every signed-in member*
   — publishing a student's home coordinates would have been a genuine incident.
2. **Cost.** A 4 MB, 12-megapixel portrait was being served as-is to a 40-pixel circle
   in a chat list. On a campus network that is megabytes of mobile data for a thumbnail,
   and it multiplies with every list scrolled.

Neither is fixable in the client: anyone can upload anything, and the client cannot be
trusted to downscale. So the server normalises.

## 2. What happens to an uploaded picture

```
upload → magic-number check → byte cap (2 MB) → decode → pixel-budget check
       → EXIF orientation applied → square centre crop → resize 512
       → WebP re-encode (metadata is gone because nothing is copied) → stored
```

| Concern | Handling |
| --- | --- |
| Metadata / GPS | never copied: the stored file is a fresh encode of pixels only (tested: `exif == {}` and no GPS IFD) |
| Sideways phone photos | EXIF `Orientation` is applied to the pixels **before** the metadata is dropped (tested with a red corner marker) |
| Distortion | `ImageOps.fit` centre-crops, so a 16:9 or 3:4 photo stays square without squashing faces |
| Decompression bombs | a 69-byte PNG claiming 30000×30000 (3.6 GB decoded) is refused **before** decoding, via the pixel budget + Pillow's own guard |
| Corrupt files | a valid JPEG header with no image behind it is refused at decode; nothing is left on disk |
| Documents | **not** processed — an ID card or registration book is stored byte-for-byte, because an administrator has to read it (tested) |

## 3. Measured on the production stack

nginx + TLS + gunicorn + `ENVIRONMENT=production`, uploading a 12 MP phone photo with a
GPS tag and an orientation flag:

| Step | Result |
| --- | --- |
| uploaded | **0.79 MB** · 3024×4032 · JPEG · EXIF: Make, GPS, Orientation=6 |
| stored (full) | **14,834 bytes** · 512×512 · WebP · `image/webp` · **EXIF: none** |
| `?size=thumb` | **176 bytes** · 128×128 · WebP · separate ETag (`"thumb-…"`) |
| compression | **53×** here; 79× on a noisier 2.65 MB original (34.4 KB) |
| normalisation cost | **248 ms** for a 12 MP decode on this 2-vCPU box (one-off, per upload) |
| thumbnail cost | 8.3 ms cold, **0.0 ms warm** (in-process LRU + client cache) |
| document upload | 263,643 bytes in → **263,643 bytes stored**, unchanged |
| decompression bomb | `422 PHOTO_TOO_LARGE · "This photo is too large to process."` |

Console (Playwright over the dev server): **13 rows · 3 avatars decoded · 6/6 photo
requests used `size=thumb`**, all `200 image/webp` → `documentation/screenshots/phase14-thumbnails.png`.

## 4. Design decisions worth defending

**The original is not kept.** For documents, the original file *is* the evidence, so it
is preserved. For a face it is not: keeping the raw upload would preserve exactly the
metadata this phase exists to remove. Members who want the original still have it on
their phone.

**The thumbnail is derived, not stored.** The source is 512 px; resizing to 128 px costs
a few milliseconds, the result is cached in-process (256 entries) and the client caches
it for an hour against a versioned URL. Storing a second file would need a schema change
and a second orphan-sweep rule for a saving that does not exist at this scale.

**The cap applies to the upload, not the result.** A 12 MP photo at maximum JPEG quality
can exceed 2 MB even though the stored avatar is 15 KB. The mobile client downscales to
`quality: 0.6` before sending (Phase 13), so the realistic path fits; a member who picks
a huge file is told plainly which limit they hit.

**Documents are deliberately exempt.** Re-encoding an ID card is how text becomes
unreadable at exactly the moment an administrator needs to read it.

## 5. What this still does not do

* **No virus scanning.** Magic numbers plus a real decode stop the naive attacks
  (a PHP script named `.png` will not decode), not a determined one. ClamAV integration
  is the next step if uploads ever leave the university network.
* **No server-side object storage or CDN.** Files live on the local volume, unchanged
  from Phase 9. With normalisation the volume now grows at ~15 KB per member, which is
  a rounding error for the pilot.
* **No photo moderation queue.** Reported in doc 19 §6 and still true: an administrator
  can see and act on an account, but a member cannot report a specific picture.
* **WebP only.** Every client that matters (Android, iOS 14+, all current browsers)
  decodes it; a PNG fallback for ancient clients was not worth the second code path.
* **The in-process thumbnail cache is per worker.** With five gunicorn workers, a face
  may be resized once per worker. At 0.0 ms warm and 8.3 ms cold this is irrelevant.
