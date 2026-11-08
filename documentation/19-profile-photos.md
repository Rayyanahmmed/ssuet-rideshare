# 19 · Phase 13 — profile photos

**Status:** complete. The last "paste a link" field in the product is gone: a member
uploads a face, every other member sees it everywhere the app shows a person.

```
backend$  python -m pytest tests/test_profile_photos.py      # 22 passed (387 total, 94 %)
backend$  python -m scripts.check_contracts                  # 98 / 98
mobile$   npx tsc --noEmit && npx expo export -p android      # clean · 4,204,699 B bundle
console$  npm run build                                       # 796 K dist
```

---

## 1. The gap this closes

Every other field that used to be "a URL somebody typed" became a real upload in
Phases 9 and 10 — ID cards, then vehicle photos and registration books. Profile photos
were the exception: `users.profile_photo_url` was still an `HttpUrl` a member had to
find somewhere and paste. Nothing validated it, nothing served it, and the app's
`<Avatar>` fell back to initials for every member, always.

The interesting part is not the upload. It is that a face is **semi-public**: an ID card
must stay visible only to its owner and an administrator, but a profile photo has to be
readable by every signed-in student, or it is useless. The design has to hold both
truths at once without weakening the rule that protected the ID cards.

## 2. The design decision

| Rule | How it is enforced |
| --- | --- |
| ID cards stay private | `/media/{id}` still allows only the owner and admins (unchanged) |
| Faces are visible in the community | new `GET /users/{id}/photo`, any **authenticated** member |
| Nothing public on the internet | no static mount; anonymous requests get **401** |
| The asset id is not a capability | holding an avatar's asset id still 403s at `/media/{id}` — tested |
| Cache-friendly | the URL carries the asset id (`?v=…`), so a new upload is a new URL |

`User.photo_url` (a Python property) decides what clients receive: the uploaded photo
first, the legacy external link as a fallback, `null` otherwise. Every payload that
already had a `profile_photo_url` field now fills it from one place — ride cards,
public profiles, chat counterparts, trips, reviews, reports, requests and the admin
member list — so the app shows a face wherever it shows a person.

## 3. What shipped

| Layer | Change |
| --- | --- |
| Storage | `users.profile_photo_asset_id` → `media_assets.id`, `ON DELETE SET NULL` (migration `9d31c4f8a2b7`) |
| Upload | `POST /users/me/photo` — JPG/PNG/WebP **by magic number**, ≤ 2 MB (`MAX_PROFILE_PHOTO_BYTES`), 10/min |
| Remove | `DELETE /users/me/photo` — row and file deleted, legacy link preserved |
| Read | `GET /users/{id}/photo` — members only; `ETag`, `Cache-Control: private, max-age=3600`, `nosniff` |
| Replacing | the previous file is deleted **immediately**, not left for the sweep |
| Housekeeping | the orphan sweep now knows a third reference set, so an avatar is never collected |
| Admin | an avatar column in the member list and in the dossier drawer, fetched as a blob with the token |
| Mobile | `<Avatar>` renders the photo (token sent as a header), camera badge + "Add/Change/Remove photo" on the profile screen |

## 4. Evidence, through the production stack

nginx + TLS + gunicorn + `ENVIRONMENT=production`, photographed with a synthetic avatar
for the seeded member `fatima@ssuet.edu.pk`:

```
=== 1. upload through nginx + TLS ===
  profile_photo_url: /api/v1/users/faa61f52-…/photo?v=83442316-…
=== 2. a different member reads it (ali@) ===
  status 200 · 2623 bytes · image/png
  cache-control: private, max-age=3600 · etag: "584768550c9390688dce61f20200eba5"
  bytes identical to what was uploaded: YES
=== 3. an outsider is refused ===
  anonymous read → 401
=== 4. the photo reaches the payloads other clients read ===
  GET /users/{id}/public  ✓   GET /admin/users ✓   GET /rides (Explore) → 3 / 7 drivers
=== 5. rejections, through the proxy ===
  PDF declared → VALIDATION_ERROR · "Upload a JPG, PNG or WebP image."
  3 MB body    → 413 · FILE_TOO_LARGE · "This file is larger than 2 MB."
```

In the console (Playwright, over `https://rideshare.ssuet.edu.pk`): **14 member rows,
4 photos decoded, 10 initials fallbacks, dossier drawer shows the photo, 0 console
errors** → `documentation/screenshots/phase13-profile-photos.png`.

`deploy/smoke.sh` gained a 17th check — `GET /users/{id}/photo` without a token must be
**401** — and passes **17/17** against the live stack.

## 5. Two things worth recording

**The 2 MB cap is deliberately lower than the 5 MB document cap.** A phone camera photo
is 4–8 MB, so a member who picks one and uploads it would otherwise be refused with a
message about documents. The client downsizes before upload (`quality: 0.6`, square
crop) and the server enforces its own smaller limit — both are tested, including that a
3 MB file is a legal *document* and an illegal *avatar*.

**The foreign key is `use_alter`.** `users → media_assets → users` is a genuine cycle,
and SQLAlchemy could not order `CREATE`/`DROP` statements, which broke `drop_all` in the
test fixtures with `no such table: main.rides` — a failure that looked like an unrelated
schema bug. Naming the constraint and deferring it to `ALTER` resolved it. This is the
kind of thing a "small" feature hides.

## 6. What this still does not do

* **No image processing.** Uploads are stored byte-for-byte; no resizing, cropping,
  EXIF stripping, or thumbnails. A 512×512 avatar and a 12-megapixel camera photo cost
  the same to serve. Worth adding when there is an image library in the deployment
  (thumbnails would cut mobile data noticeably).
* **No moderation queue for faces.** An administrator can *see* every photo in the
  console and suspend an account, but there is no "report this photo" path and no
  approval step. Reports already exist for trips; a photo report would be a small
  extension of the same machinery.
* **No virus scan / S3.** Unchanged from Phase 9: magic-number sniffing stops the
  trivial attacks, not a determined one.
* **Photo change is not audited** in `admin_actions` (uploads are logged by the media
  logger, with the request id, but not in the audit table).
