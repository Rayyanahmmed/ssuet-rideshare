# 15 · Phase 9 — media upload pipeline (verification documents)

**Status:** complete. 24 new tests (338 total, 94 % coverage). Verification documents
now live inside the platform instead of behind a pasted Drive link — the last
workaround listed in doc 12 §6 and doc 14 §6 is gone.

```bash
backend$  python -m pytest tests/test_uploads.py -v      # 24 passed
backend$  alembic upgrade head                           # 0ff2be74d4a7 (media_assets)
mobile$   npx tsc --noEmit                               # clean
admin-dashboard$ npx tsc --noEmit && npm run build        # clean
```

---

## 1. Why this came next

The Phase 8 audit ended with a short list of honest gaps. The largest was that a
member proving who they are had to upload a photo of their student card to Google
Drive and paste the link — which meant a student ID sat in a third-party account,
the link could be shared with anyone, the reviewer had no way to know the file was
still there, and the mobile screen apologised for a "media pipeline" that had never
been built. Everything else on that list (Maps, SMTP, push keys) is configuration the
operator supplies; this was missing software.

## 2. What shipped

| Layer | Addition |
| --- | --- |
| Storage | `media_assets` table — owner, purpose, relative path, content type, size, SHA-256, original filename. Migration `0ff2be74d4a7` adds it and a nullable `verifications.document_asset_id`. |
| Upload | `POST /uploads/verification` — multipart, 5 MB cap, validation by content. |
| Read | `GET /media/{id}` — streamed to the owner or to an administrator; never a public static mount. |
| Withdraw | `DELETE /media/{id}` — owner or administrator; removes the row and the file. |
| Verification | `POST /users/me/verification` takes **either** `document_asset_id` **or** `document_url`, never both and never neither. |
| Admin queue | Rows carry `document_asset_id`; the console fetches the image with the admin token and opens it in a tab. |
| Mobile | “Choose photo” / “Take photo” with an inline preview; the pasted link stays as a fallback. |

## 3. Security properties (and the tests that hold them)

Uploads are the classic place where a web app is compromised, so each rule has a
test rather than a comment:

1. **Content, not extension.** The first bytes are matched against JPEG / PNG /
   WebP / PDF magic numbers. A shell script named `card.jpg` is rejected with 422,
   and a PNG named `card.jpg` that declares `image/jpeg` is stored as `image/png`.
2. **The client never chooses the path.** Stored names are `uploads/YYYY/MM/<uuid>.<ext>`;
   `../../../etc/passwd.png` lands harmlessly inside the media root. Display names are
   sanitised to `[A-Za-z0-9._-]`.
3. **The cap is enforced while streaming**, chunk by chunk, so an oversize upload is
   abandoned at the limit and the partial file is deleted — the disk never holds a
   6 MB request that only had a 5 MB budget.
4. **Reads are authorised per request.** `GET /media/{id}` checks the row: the owner
   or an administrator, nobody else (403 otherwise; 401 unauthenticated; a stranger's
   upload id in a verification submission is a 404, so ids cannot be probed).
5. **Response headers cannot be reinterpreted**: `X-Content-Type-Options: nosniff`,
   `Cache-Control: private, no-store`, `Content-Disposition: inline`.
6. **Nothing is public.** There is no `/media` static mount. A leaked URL is worth
   nothing without a matching token.

## 4. The API, concretely

```http
POST /api/v1/uploads/verification          (multipart/form-data, field "file", 10/min)
→ 201 {
    "id": "57119f78-…", "purpose": "VERIFICATION_DOCUMENT",
    "content_type": "image/png", "byte_size": 75,
    "checksum_sha256": "3f0a…", "original_filename": "ssuet-card.png",
    "url": "/api/v1/media/57119f78-…", "created_at": "2026-11-06T10:33:12Z"
  }

POST /api/v1/users/me/verification
{ "verification_type": "STUDENT_ID", "submitted_value": "SSUET-2026-123",
  "document_asset_id": "57119f78-…", "note": "Uploaded from the app" }
→ 201 { …, "document_asset_id": "57119f78-…", "document_url": null, "status": "PENDING" }

GET    /api/v1/media/{id}   → 200 image/png (owner or admin)
DELETE /api/v1/media/{id}   → 204 (owner or admin)
```

Errors use the standard envelope: `VALIDATION_ERROR` (422) for an unknown type,
`FILE_TOO_LARGE` (413) above the cap, `FORBIDDEN` (403) for a stranger, `NOT_FOUND`
(404) for an unknown or withdrawn asset.

## 5. Live verification (executed, not asserted)

Run against the seeded development database with the API on :8000.

| # | Step | Result |
| --- | --- | --- |
| 1 | Register a member with a non-university email | 201, needs manual verification |
| 2 | Upload a PNG card photo | 201, 75 B, `image/png` |
| 3 | Upload a shell script renamed `evil.jpg` | 422 `VALIDATION_ERROR` |
| 4 | Upload PNG bytes + 6 MB of padding | 413 `FILE_TOO_LARGE` |
| 5 | Submit verification with `document_asset_id` | 201, `PENDING`, `document_url: null` |
| 6 | Owner reads the file back | 200, bytes identical, `nosniff` |
| 7 | Another member reads it | 403 `FORBIDDEN` |
| 8 | Admin queue | row shows the upload (`document_asset_id` populated) |
| 9 | Admin downloads it | 200, `inline; filename="ssuet-card.png"` |
| 10 | Admin approves the member | 200, `VERIFIED` |
| 11 | Owner withdraws the upload, admin re-requests it | 204 then 404 |

**11/11.** Browser check of the console (Playwright, live API): the queue renders a
**View upload** button for the uploaded card and `—` for the older link-less row;
clicking it opens a `blob:` tab with the decoded image (480×300) and **0 console
errors**.

| Screenshot | Shows |
| --- | --- |
| `screenshots/phase9-verification-queue.png` | verification queue with the **View upload** action |
| `screenshots/phase9-document-viewer.png` | the uploaded card opened in the viewer tab (served from `GET /media/{id}` with the admin token) |

A demo row is left in the seeded database for the FYP demo:
**Ayesha Khan · ayesha8b3933@gmail.com · Password123** — pending verification with a
4 KB card photo already uploaded, so the reviewer flow can be demonstrated live.

## 6. Configuration

```bash
# backend/.env
MEDIA_ROOT=./media                # point at a mounted volume in production
MAX_UPLOAD_BYTES=5242880          # 5 MB (allowed range: 64 KB – 25 MB)
```

`media/` is gitignored. The mobile screen mirrors the 5 MB cap before uploading, so
a member on a slow connection is told immediately rather than after a 30 s POST.

**Operational note (doc 13 §9):** uploads are files, so they are not covered by a
database dump. Back up `MEDIA_ROOT` alongside the database, and watch its size —
ballpark 200–400 KB per verified member, which is nothing for a university of this
size but should be on the runbook's radar.

## 7. What this deliberately does not do

* **No image processing.** Files are stored as sent (after validation). No thumbnail
  generation, no EXIF stripping, no OCR. If ID-forensics is ever wanted, that is a
  background job, not a request-time step.
* **No virus scanning.** A production deployment in front of a real user base should
  add ClamAV or a cloud scanner on the upload path; the seam is `media_service.store_upload`.
* **No S3.** Local disk with a mounted volume is right for one server; swapping in
  object storage means replacing `media_service` only, because callers use asset ids.
* ~~Orphans are not swept yet.~~ **Fixed in Phase 10** — `scripts/sweep_media.py` and the
  housekeeping run delete uploads that no verification *or vehicle* references once they
  are older than `MEDIA_ORPHAN_RETENTION_DAYS`. See
  [`16-phase10-vehicle-documents.md`](16-phase10-vehicle-documents.md).
