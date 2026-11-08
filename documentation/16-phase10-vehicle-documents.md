# 16 · Phase 10 — vehicle documents & media housekeeping

**Status:** complete. 15 new tests (353 total, 94 % coverage). Vehicles now carry
uploaded proof instead of external links, and uploads that never became part of a
record are swept automatically — the two loose ends Phase 9 left behind.

```bash
backend$  python -m pytest tests/test_media_housekeeping.py -v   # 15 passed
backend$  alembic upgrade head                                   # 1ecaa4a7e72e
backend$  python -m scripts.sweep_media --stats
mobile$   npx tsc --noEmit                                       # clean
admin-dashboard$ npx tsc --noEmit && npm run build                # clean
```

---

## 1. Why

Phase 9 gave verification documents a real home. Two things were still missing:

1. **Vehicles.** An administrator approving a car had the same problem the
   verification queue used to have — the proof of registration was a pasted link, or
   nothing at all. The console could not tell a careful reviewer anything about the
   car in the photo.
2. **Orphans.** A member who picks a photo and never submits the form leaves a file on
   disk forever. Phase 9's doc 15 §7 listed the sweep as known-missing; a limitation
   you can name is fine, one you can fix cheaply is better.

## 2. What shipped

| Layer | Addition |
| --- | --- |
| Schema | `vehicles.photo_asset_id`, `vehicles.registration_asset_id` (nullable, `ON DELETE SET NULL`), migration `1ecaa4a7e72e` |
| Upload | `POST /uploads/vehicle` — same validation, limits and rate limit as the verification upload; purpose `VEHICLE_DOCUMENT` |
| Vehicles | `POST /vehicles` / `PATCH /vehicles/{id}` accept both ids; ownership and purpose are enforced server-side |
| Sweep | `media_service.sweep_orphans()` + `scripts/sweep_media.py` (`--dry-run`, `--days`, `--stats`), also folded into the housekeeping run |
| Admin API | `GET /admin/media` — files, bytes, orphans, oldest file, retention window |
| Mobile | Vehicle form: “Add a photo of the vehicle” and “Add the registration book”, uploaded immediately, previous upload withdrawn when replaced |
| Console | **Proof** column in Vehicle verification: *Vehicle photo* / *Registration book* buttons that stream the file with the admin token |

## 3. Rules (the same ones, applied twice)

* An upload id is only accepted if **it belongs to the caller** (404 otherwise) and has
  the **purpose that matches the slot** (422 otherwise). A verification card cannot be
  reused as a registration book, and one member cannot attach another member's file to
  their vehicle.
* Reads stay authorised per request: owner or administrator. `GET /media/{id}` does not
  care which purpose the file has.
* An orphan is a file **no** verification and **no** vehicle references. The sweep
  refuses to touch anything younger than `MEDIA_ORPHAN_RETENTION_DAYS` (7 by default),
  because a file that is minutes old may simply be mid-flow.
* The sweep removes the row *and* the file, and reports bytes reclaimed so the runbook
  can show it working.

## 4. The sweep, concretely

```bash
$ python -m scripts.sweep_media --stats
files=4 size=5.0 KB orphans=1 orphan_size=75.0 B retention=7d

$ python -m scripts.sweep_media --dry-run
[dry-run] orphans deleted=1 reclaimed=75.0 B referenced_kept=3 within_retention=0

$ python -m scripts.sweep_media
orphans deleted=1 reclaimed=75.0 B referenced_kept=3 within_retention=0

$ python -m scripts.sweep_media --stats
files=3 size=5.0 KB orphans=0 orphan_size=0.0 B retention=7d
```

The same work happens inside the in-process housekeeping run every 15 minutes
(`MAINTENANCE_INTERVAL_MINUTES`); the CLI exists for deployments that keep the API
stateless and prefer cron:

```cron
30 3 * * * cd /srv/ssuet-backend && .venv/bin/python -m scripts.sweep_media
```

## 5. Live verification (executed)

Against the seeded development database, API on :8000.

| # | Step | Result |
| --- | --- | --- |
| 1 | Register a driver | 201 |
| 2 | Upload a vehicle photo | 201, `VEHICLE_DOCUMENT`, 75 B |
| 3 | Upload the registration book | 201 |
| 4 | Register the vehicle with both ids | 201, `PENDING`, both ids echoed |
| 5 | Admin vehicle queue | row carries both ids for the Proof column |
| 6 | Admin downloads the registration book | 200, bytes identical |
| 7 | `GET /admin/media` | `files=3 bytes=5085 orphans=0 retention=7d` |
| 8 | Admin approves the vehicle | 200, `VERIFIED` |
| 9 | Register a bike pointing at an unknown upload id | 404 `NOT_FOUND` |
| 10 | Abandoned upload backdated 10 days | sweep reports 1 orphan, dry run deletes nothing |
| 11 | Real sweep run | deletes 1 file, keeps 3 referenced, stats return to `orphans=0` |

**11/11.** Browser check (Playwright): the Vehicle verification table renders a **Proof**
column, *Vehicle photo* and *Registration book* open `blob:` tabs with the decoded
image, 0 console errors — `documentation/screenshots/phase10-vehicle-proof.png`.

## 6. Configuration

```bash
MEDIA_ROOT=./media
MAX_UPLOAD_BYTES=5242880
MEDIA_ORPHAN_RETENTION_DAYS=7      # sweep grace window (1–365)
```

Runbook additions (doc 13 §8): the sweep cron line, how to read `GET /admin/media`, and
what to do when the console shows a proof button but the file is gone.

## 7. Deliberately still out of scope

* **No OCR / plate recognition.** The reviewer compares the photo and the book by eye;
  automating that is a research project, not a phase.
* **No object storage.** `media_service` is the only module that knows files live on
  disk — swapping in S3 means rewriting that one file.
* **No virus scanning.** Unchanged from doc 15 §7: add a scanner at
  `media_service.store_upload` before exposing this to a wider audience.
* **Vehicle documents are not required.** A vehicle can still be registered with no
  proof at all (the seeded demo data has none). If SSUET ever wants mandatory papers,
  the change is a policy flag next to `REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH`, not a
  schema change — the column already exists.
