# 3. API Contracts — `/api/v1`

Base URL: `http://<host>:8000/api/v1` · Swagger: `/docs` · ReDoc: `/redoc`

**Legend:** ✅ implemented in Phase 1 · 🔜 planned (phase in brackets)

## 3.1 Conventions

* **Auth:** `Authorization: Bearer <access_jwt>` on every protected route.
* **Errors** (one shape everywhere):
  ```json
  {"error": {"code": "RIDE_NOT_AVAILABLE", "message": "This ride has just been taken by another passenger.", "details": {}}}
  ```
* **Pagination:** cursor for feeds — `?cursor=<iso8601>&limit=20`; page-based for
  admin tables — `?page=1&page_size=25`.
* **Timestamps:** ISO-8601 UTC (`2026-11-07T03:00:00Z`).
* **Rate limits** (SlowAPI, per IP + per user): login 5/min, register 3/min,
  forgot-password 3/hour, request-ride 10/min.
* **Errors codes in use:** `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`,
  `NOT_FOUND`, `CONFLICT`, `RIDE_NOT_AVAILABLE`, `RATE_LIMITED`,
  `ACCOUNT_SUSPENDED`, `ACCOUNT_NOT_VERIFIED`.

## 3.2 System ✅

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/health/ready` | DB readiness |
| GET | `/meta` | university coords, `maps_configured`, feature flags |

## 3.3 Authentication — `/auth` ✅ Phase 2

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/auth/register` ✅ | `full_name, email, password, phone, role, university_id, department, semester?, designation?, home_area?` → 201 + token pair. `verification_status=VERIFIED` when the email domain is trusted (and `AUTO_VERIFY_UNIVERSITY_EMAILS`), otherwise `UNVERIFIED` until an ID is submitted |
| POST | `/auth/login` ✅ | `email, password` → `access_token, refresh_token, token_type, expires_in, user`. Generic 401 for wrong email *or* password; 403 `ACCOUNT_SUSPENDED` when suspended |
| POST | `/auth/refresh` ✅ | `refresh_token` → new pair (**rotation**); replay of a consumed token revokes every session of that user |
| POST | `/auth/logout` ✅ · `/auth/logout-all` ✅ | revoke one / all sessions |
| POST | `/auth/forgot-password` ✅ | `email` → always 202 (no account enumeration); token single-use, 30 min TTL |
| POST | `/auth/reset-password` ✅ | `token, new_password` → revokes every existing session |
| POST | `/auth/verify-email` ✅ · `/auth/resend-verification` ✅ | confirm the email address (single-use token) |
| GET | `/auth/me` ✅ · POST `/auth/change-password` ✅ | owner view of the account |

## 3.4 Users & vehicles — `/users` ✅ Phase 2, `/vehicles` ✅ Phase 3

| Method | Path | Purpose |
|---|---|---|
| GET | `/users/me` ✅ | full profile |
| PATCH | `/users/me` ✅ | update name/photo/department/phone/home area — role, verification and statistics can never be self-assigned |
| POST | `/users/me/verification` ✅ | submit student/employee ID with `document_asset_id` (upload) **or** `document_url` (link) → `PENDING` |
| GET | `/users/me/verifications` ✅ | verification audit trail |
| GET | `/users/{id}/public` ✅ | name, photo, role, department, badge, rating, trips (no email/phone/university ID/home area) |
| POST | `/users/me/photo` ✅ Phase 13–14 | multipart profile photo — JPG/PNG/WebP **by magic number**, ≤ `MAX_PROFILE_PHOTO_BYTES` (2 MB), 10/min. Stored **normalised**: EXIF/GPS stripped, orientation applied, square-cropped, resized to `PROFILE_PHOTO_MAX_DIMENSION` (512), re-encoded WebP — so `byte_size` is the stored size. Refuses files over `MAX_PHOTO_PIXELS` (40 MP) without decoding them |
| DELETE | `/users/me/photo` ✅ Phase 13 | removes the picture and the stored file; falls back to the legacy link |
| POST | `/users/{id}/photo/report` ✅ Phase 15 | `{reason: OFFENSIVE\|NOT_A_REAL_PERSON\|IMPERSONATION\|OTHER, description}` → a `PROFILE_PHOTO` report with the **current asset pinned** as evidence; 5/min; one open photo report per member; 404 when the member has no photo, 422 on self-report |
| GET | `/users/{id}/photo` ✅ Phase 13–14 | streams the photo to **any signed-in member** — unlike `/media/{id}`, which stays owner+admin. `?size=thumb` returns the 128 px variant (same ETag scheme, own value) |
| GET | `/users/{id}/reviews` ✅ | paginated reviews (empty until Phase 7 writes them) |
| POST | `/users/{id}/block` ✅ · DELETE ✅ · GET `/users/me/blocks` ✅ | block / unblock / list |
| GET | `/vehicles` | my vehicles |
| POST | `/vehicles` | register car/bike (optionally with `photo_asset_id` / `registration_asset_id`) → `status=PENDING` |
| PATCH | `/vehicles/{id}` · DELETE | edit / soft delete |

## 3.5 Rides — `/rides` ✅ Phase 3

| Method | Path | Purpose |
|---|---|---|
| POST | `/rides` | publish journey (direction, areas + coords, departure date/time, vehicle, seats=1, fuel preference, note) |
| GET | `/rides` | explore feed. Filters: `direction, vehicle_type, fuel_preference, date_from, date_to, departure_after, departure_before, area, lat, lng, radius_km, cursor, limit` |
| GET | `/rides/{id}` | details (precise coords only if matched viewer) |
| PATCH | `/rides/{id}` | edit **while `OPEN`** only |
| POST | `/rides/{id}/cancel` | driver cancels (notifies passenger + pending requesters) |
| POST | `/trips/{id}/start` | `CONFIRMED → IN_PROGRESS` — driver only (moved from `/rides/{id}/start` in Phase 4) |
| POST | `/trips/{id}/complete` | both sides must confirm before `COMPLETED` (moved from `/rides/{id}/complete`) |
| GET | `/rides/mine` | `?status=open|matched|completed|cancelled` |
| GET | `/rides/{id}/requests` | driver-only inbox |

## 3.6 Requests — `/requests` ✅ Phase 3 (trip-side actions in Phase 4)

| Method | Path | Purpose |
|---|---|---|
| POST | `/rides/{ride_id}/requests` | passenger asks to join `{message?}` |
| GET | `/requests/mine` | my outgoing requests |
| POST | `/requests/{id}/accept` | driver accepts → trip + conversation + notifications (atomic) |
| POST | `/requests/{id}/reject` | driver rejects `{note?}` |
| POST | `/requests/{id}/cancel` | passenger withdraws a pending request |

## 3.7 Trips — `/trips` ✅ Phase 4

| Method | Path | Purpose |
|---|---|---|
| GET | `/trips/mine` | `?status=upcoming|active|completed|cancelled` |
| GET | `/trips/{id}` | trip detail (participants + admin only) |
| POST | `/trips/{id}/start` | `CONFIRMED → IN_PROGRESS` |
| POST | `/trips/{id}/complete` | both sides confirm → `COMPLETED`, increments counters |
| POST | `/trips/{id}/cancel` | either side, `{reason}` |
| POST | `/trips/{id}/no-show` | driver marks passenger absent |

## 3.8 Chat — `/chat` ✅ Phase 5

| Method | Path | Purpose |
|---|---|---|
| GET | `/chat/conversations` | my threads with last message + unread count |
| GET | `/chat/conversations/{id}/messages` | history `?cursor=&limit=30` |
| POST | `/chat/conversations/{id}/messages` | REST fallback for sending |
| POST | `/chat/conversations/{id}/read` | mark read |
| WS | `/api/v1/chat/ws?token=<jwt>` | realtime. Server events: `message.created`, `message.read`, `typing`, `trip.updated`. Only the two trip participants may join a room. |

## 3.9 Notifications — `/notifications` ✅ Phase 5

| Method | Path | Purpose |
|---|---|---|
| GET | `/notifications` | paginated history + `unread_count` |
| POST | `/notifications/{id}/read` · `/notifications/read-all` | mark read |
| GET / POST | `/notifications/devices` | list / register an Expo push token (upsert by token) |
| DELETE | `/notifications/devices/{token}` | remove on logout |

## 3.10 Reviews & reports — `/reviews`, `/reports` ✅ Phase 7

Shipped shape — the authoritative table with every guard is §3.10a below.

| Method | Path | Purpose |
|---|---|---|
| POST | `/reviews/trips/{trip_id}` | `{rating 1-5, comment?}`; participant + completed only + once per side |
| GET | `/reviews/pending` · `/reviews/me/received` · `/reviews/users/{user_id}` | what I owe / what I received / any member's ratings |
| POST | `/reports` | `{category, description, reported_user_id?, trip_id?, ride_id?}` — subject derived from the journey |
| GET | `/reports` · `/reports/{report_id}` | my reports and their outcome (renamed from `/reports/mine` in Phase 7) |
| POST / DELETE | `/users/{user_id}/block` · GET `/users/me/blocks` | blocking (§15) |

## 3.10a Phase 7 reviews, reports & blocking — implemented and verified

All routes require a signed-in, active member. Reviews and reports are separate
resources because they answer different questions: a **rating** builds reputation,
a **report** asks the university to intervene.

### Reviews — `/reviews`

| Method | Path | Body / query | Rules |
|---|---|---|---|
| POST | `/reviews/trips/{trip_id}` | `{rating: 1–5, comment?: 3–500 chars}` → `201 ReviewOut` | trip must be `COMPLETED` (`409`), caller must be a participant (`403`), one review per side (`409`), comment whitespace-collapsed |
| GET | `/reviews/pending` | — | completed trips where the caller's review flag is still false |
| GET | `/reviews/me/received` | `page`, `limit` | reviews about me |
| GET | `/reviews/users/{user_id}` | `page`, `limit` | `ReviewPage`: `items`, `total`, `average`, `breakdown {"5"…"1"}`; hidden reviews excluded |

`ReviewOut` = `id, trip_id, rating, comment, direction, pickup_area,
destination_area, author{id, full_name, profile_photo_url, role, department},
subject_id, created_at`. The subject's `rating_average` / `rating_count` are
**recomputed** from visible rows on every write and every moderation decision.

### Reports — `/reports`

| Method | Path | Body / query | Rules |
|---|---|---|---|
| POST | `/reports` | `{category, description: 10–1000, reported_user_id? , trip_id?, ride_id?}` → `201 ReportOut` | at least one of member/trip/ride required; with `trip_id` the subject must be the other participant (`422` otherwise) and the caller must be on it (`403`); with `ride_id` the subject must be the driver or a requester; self-report `422`; a second **open** report for the same pair `409` |
| GET | `/reports` | `status`, `page`, `limit` | only reports the caller filed |
| GET | `/reports/{report_id}` | — | owner only — another member's id is `404`, not `403` |

`ReportOut` = `id, category, description, status, reported_user{…},
trip_id, ride_id, resolution_note, resolved_at, created_at`.

Categories: `INAPPROPRIATE_BEHAVIOR`, `FAKE_PROFILE`, `MISLEADING_RIDE`,
`HARASSMENT`, `SAFETY_CONCERN`, `OTHER`.
Statuses: `OPEN → UNDER_REVIEW → RESOLVED | DISMISSED`.
A filed report acknowledges the reporter (`REPORT_RECEIVED`) and creates a system
notification for every active admin; resolving it notifies the reporter with the
written note (`REPORT_RESOLVED`).

### Blocking — `/users`

| Method | Path | Effect |
|---|---|---|
| POST | `/users/{user_id}/block` | the pair can never be matched; the blocked member's rides leave Explore; chat is refused with `403` |
| DELETE | `/users/{user_id}/block` | unblock |
| GET | `/users/me/blocks` | members I blocked |

### Review moderation — `/admin`

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/reviews` | `hidden`, `search`, `min_rating`, `max_rating`, `page`, `limit`; rows carry `has_report` |
| POST | `/admin/reviews/{review_id}/hide` | `{reason}`; recomputes the subject's average; audited as `HIDE_REVIEW` |
| POST | `/admin/reviews/{review_id}/unhide` | `{note?}`; audited as `UNHIDE_REVIEW` |

### Rate limits added in Phase 7

| Endpoint | Limit |
|---|---|
| `POST /reviews/trips/{id}` | 10 / minute |
| `POST /reports` | 5 / minute |

## 3.10b Media uploads — `/uploads`, `/media` ✅ Phase 9

The full rationale, threat model and evidence are in
[`15-phase9-media-pipeline.md`](15-phase9-media-pipeline.md). Summary:

| Method | Path | Purpose | Guards |
|---|---|---|---|
| POST | `/uploads/verification` | multipart upload of an ID card or fee receipt (purpose `VERIFICATION_DOCUMENT`) | auth required · 10/min per IP · JPG/PNG/WebP/PDF by magic bytes (not extension) · ≤ `MAX_UPLOAD_BYTES` (5 MB) · stored as `uploads/YYYY/MM/<uuid>.<ext>` |
| POST | `/uploads/vehicle` | multipart upload of a vehicle photo or registration book (purpose `VEHICLE_DOCUMENT`) | same validation and limits |
| GET | `/media/{id}` | stream a stored file | owner **or** `role=ADMIN`; 401 unauthenticated, 403 stranger, 404 unknown/withdrawn · `nosniff`, `private, no-store`, `inline` |
| DELETE | `/media/{id}` | withdraw an upload | owner or ADMIN · deletes the row and the file |

Errors: `VALIDATION_ERROR` (unknown type / empty file), `FILE_TOO_LARGE` (413),
`FORBIDDEN`, `NOT_FOUND`. There is **no** public static mount for `MEDIA_ROOT`.

`POST /users/me/verification` accepts exactly one document source — sending both
`document_asset_id` and `document_url` (or neither) is a 422. `POST /vehicles` and
`PATCH /vehicles/{id}` accept `photo_asset_id` and/or `registration_asset_id` from
`/uploads/vehicle`; an upload id that belongs to someone else is a 404, and one with
the wrong purpose (e.g. a verification card reused as a registration book) is a 422.

`GET /admin/media` (admin only) reports storage health: `files`, `bytes`, `orphans`,
`orphan_bytes`, `oldest`, `retention_days`, `max_upload_bytes`.

## 3.10c Operations & health ✅ Phase 12

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/health` | liveness | never touches the database — answers while the DB is down |
| GET | `/health/ready` | readiness | one `SELECT 1`; the load-balancer probe |
| GET | `/admin/health` | deep health for a person | admin only · DB latency, dialect, **schema revision vs head**, pool, queue sizes, media + disk, last housekeeping run, `warnings[]`, `status: ok\|degraded` |

Every response also carries `X-Request-ID` (echoed if supplied, generated otherwise),
`X-Process-Time-Ms` and `Server-Timing: app;dur=…`. Requests slower than
`SLOW_REQUEST_MS` (default 500 ms) are logged with the same request id.

## 3.11 Admin — `/admin` ✅ Phase 6 (all routes require `role=ADMIN`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/dashboard` | stat cards + chart series (users/rides/trips over time) |
| GET | `/admin/users` | `?search=&role=&status=&verification=&page=` |
| GET | `/admin/users/{id}` | full profile incl. vehicles, rides, reports |
| POST | `/admin/users/{id}/verify` · `/reject` | manual verification (+ notification + `admin_actions`) |
| POST | `/admin/users/{id}/suspend` · `/reactivate` | `{reason}` |
| GET | `/admin/verifications` | queue `?status=PENDING` |
| GET | `/admin/vehicles` · POST `/admin/vehicles/{id}/verify|reject` | vehicle moderation |
| GET | `/admin/rides` · `/admin/trips` | `?status=&date_from=&date_to=&direction=` |
| GET | `/admin/reports` · GET `/admin/reports/{id}` · PATCH `/admin/reports/{id}` | complaint handling |
| GET | `/admin/admin-actions` | administrative action history |
| GET | `/admin/analytics` | Recharts-ready aggregates |
| GET | `/admin/settings` | runtime feature flags (read-only view of env) |

## 3.11a Phase 6 admin API — implemented and verified

Every route below is guarded by the `AdminUser` dependency: the JWT is verified **and**
`role == ADMIN` + `account_status == ACTIVE` are re-read from the database on each
request, so a token issued before a suspension stops working immediately.
Anonymous → `401`, member → `403`. List endpoints return the envelope
`{items, total, page, limit, pages}`.

| Method | Path | Key parameters / body | Notes |
|---|---|---|---|
| GET | `/admin/dashboard` | — | `stats`, `users_per_day`, `rides_per_day`, `trips_per_day` (14 points), `rides_by_status`, `trips_by_status`, `generated_at` |
| GET | `/admin/analytics` | `days` 1–180 (default 30) | growth series, `completion_rate`, `cancellation_rate`, `average_rating`, `fuel_split`, `vehicle_split`, `direction_split`, `top_pickup_areas`, `top_destinations` |
| GET | `/admin/settings` | — | environment, domains, limits and **booleans only** (`maps_configured`, `smtp_configured`, `expo_push_enabled`, …) — never a secret |
| GET | `/admin/users` | `search` (name/email/university id/phone), `role`, `status`, `verification`, `page`, `limit` | directory rows incl. rating, trip counts, vehicle count |
| GET | `/admin/users/{id}` | — | dossier: profile, `home_area`, vehicles, `recent_rides`, `verifications`, `trips_as_driver`, `trips_as_passenger`, `reports_filed`, `reports_against` |
| POST | `/admin/users/{id}/verify` | `{note?}` | `409` if already verified |
| POST | `/admin/users/{id}/reject` | `{reason}` | notification `ACCOUNT_REJECTED`-style copy via templates |
| POST | `/admin/users/{id}/suspend` | `{reason}` **required** | cancels the member's open rides; `409` for admins |
| POST | `/admin/users/{id}/reactivate` | `{note?}` | restores access |
| GET | `/admin/verifications` | `status` (default `PENDING`), `page`, `limit` | queue with `submitted_value` + `document_url` |
| GET | `/admin/vehicles` | `status`, `search`, `page`, `limit` | registration/model/owner search |
| POST | `/admin/vehicles/{id}/verify` | `{note?}` | `409` if already verified |
| POST | `/admin/vehicles/{id}/reject` | `{reason}` **required** | note is visible to the owner |
| GET | `/admin/rides` | `status`, `direction`, `search`, `date_from`, `date_to`, `driver_id`, `page`, `limit` | rows carry `matched_passenger_name` + `requests_count` |
| POST | `/admin/rides/{id}/cancel` | `{reason?}` | cascades to trips, notifies both participants |
| GET | `/admin/trips` | `status` **or** `active_only=true`, `page`, `limit` | driver/passenger names, timings |
| GET | `/admin/reports` | `status`, `category`, `page`, `limit` | complaint queue |
| GET | `/admin/reports/{id}` | — | single report |
| PATCH | `/admin/reports/{id}` | `status`, `resolution_note`, and `remove_photo` (photo reports only — deletes the member's current picture, tells them, keeps the reported file as evidence) | `{status, resolution_note?}` | note required unless `UNDER_REVIEW` |
| GET | `/admin/admin-actions` | `page`, `limit` | immutable audit log, newest first |
| GET | `/admin/ping` | — | guard check used by the console |

Every mutation writes an `admin_actions` row (`admin_id`, `action_type`, target,
`notes`, timestamp) and notifies the affected member through
`notification_service` (templates `ACCOUNT_VERIFIED`, `ACCOUNT_SUSPENDED`,
`ACCOUNT_REACTIVATED`, `VEHICLE_VERIFIED`, `VEHICLE_REJECTED`).

## 3.7a Phase 4 — implemented and verified

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/trips/mine` | participant | `role=DRIVER|PASSENGER`, `status=`, `upcoming=true|false`, `limit` ≤ 100 |
| GET | `/trips/{id}` | participants + admin | meeting point, both phones, per-side completion flags, next-action flags |
| POST | `/trips/{id}/start` | driver | `CONFIRMED → IN_PROGRESS`; `409` outside the −6 h/+12 h window |
| POST | `/trips/{id}/complete` | both | one side sets its flag; both → `COMPLETED` + counters; `409` before start / double confirm |
| POST | `/trips/{id}/cancel` | both | `{reason}`; passenger reopens the ride, driver cancels it; `409` after start (passenger) |
| POST | `/trips/{id}/no-show` | driver | `{reason}`; allowed from 30 min before departure |

`TripOut` is viewer-aware: `my_role`, `can_start`, `can_complete`, `can_cancel`,
`can_mark_no_show`, `awaiting_my_confirmation`, `can_review`, plus
`counterpart { id, full_name, department, phone }`. Full detail:
[`08-phase4-trip-lifecycle.md`](08-phase4-trip-lifecycle.md).

## 3.9a Phase 5 — implemented and verified

| Method | Path | Notes |
|---|---|---|
| GET | `/chat/conversations` | my conversations + `unread_count` each + `unread_total` |
| GET | `/chat/conversations/{id}` | participants (and admin) only, `403` otherwise |
| GET | `/chat/conversations/{id}/messages` | newest first; `next_cursor` walks backwards; `limit` ≤ 100 |
| POST | `/chat/conversations/{id}/messages` | `{body}` 1–2000 chars, trimmed; `403 BLOCKED`, `409` on a cancelled trip |
| POST | `/chat/conversations/{id}/read` | marks incoming messages read |
| WS | `/chat/ws/{conversation_id}?token=` | frames documented in `documentation/09`; close `1008` = re-authenticate |
| GET | `/notifications` | `unread_only`, cursor, `unread_count` |
| GET | `/notifications/unread-count` | badge |
| POST | `/notifications/{id}/read` · `/read-all` | mark read |
| GET/POST/DELETE | `/notifications/devices[/{token}]` | Expo token lifecycle |

Full detail: [`09-phase5-chat-notifications.md`](09-phase5-chat-notifications.md).

## 3.11b Phase 3 — implemented and verified

Live in the running API (all under `/api/v1`), matching the tables above:

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/vehicles` | list mine / register (→ `PENDING` verification) |
| PATCH/DELETE | `/vehicles/{id}` | edits return the vehicle to `PENDING`; delete blocked while on an open ride |
| POST | `/rides` | publish; campus end forced to SSUET; `seats_remaining = 1` |
| GET | `/rides` | filters: `direction, vehicle_type, fuel_preference, area, departure_after, departure_before, lat, lng, radius_km, exclude_own, limit, cursor` |
| GET | `/rides/mine` · `/rides/{id}` | detail applies the privacy projection (points/phone only for participants + admin) |
| PATCH/POST | `/rides/{id}` · `/rides/{id}/cancel` | driver-only, `OPEN`/`MATCHED` only |
| POST | `/rides/{id}/requests` | verified members, not own ride, no duplicate pending, not blocked |
| GET | `/requests/mine` · `/requests/inbox` · `/rides/{id}/requests` | requester view / driver inbox (no phone numbers) / per-ride |
| POST | `/requests/{id}/accept` | **atomic**: row lock → in-txn checks → partial unique index; returns `TripOut`; auto-rejects the rest |
| POST | `/requests/{id}/reject` · `/requests/{id}/cancel` | optional note / withdraw |

Error codes used by these endpoints: `VALIDATION_ERROR` (422), `NOT_FOUND` (404),
`FORBIDDEN` (403), `ACCOUNT_NOT_VERIFIED` (403), `CONFLICT` (409),
`RIDE_NOT_AVAILABLE` (409 — seat already taken or ride no longer open),
`RATE_LIMITED` (429).

Implementation notes, concurrency proof and mobile screen map:
[`07-phase3-ride-system.md`](07-phase3-ride-system.md).

## 3.13 Maps, APK download & password-reset fallback — added in Phase 14 ✅

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/maps/search` | member | place search (geocoding) via the configured provider |
| GET | `/maps/reverse` | member | coordinates → address |
| GET | `/maps/tiles/{z}/{x}/{y}.png` | public | map tile proxy (`.png`), keeps provider keys on the server |
| GET | `/app/download` | public | `{available, url, version, updated_at}` for the web app's APK button |
| GET | `/admin/integrations/maps` | admin | current map provider (key shown masked only) |
| PUT | `/admin/integrations/maps` | admin | change provider / key — no rebuild or redeploy |
| POST | `/admin/integrations/maps/test` | admin | validate the key with a live geocode call |
| GET | `/admin/integrations/app-download` | admin | current APK link and version |
| PUT | `/admin/integrations/app-download` | admin | `{url, version}`; empty `url` withdraws the button |
| POST | `/admin/users/{id}/password-reset-code` | admin | one-time 30-minute reset code when email is not set up; refused for non-active accounts |

## 3.12 Contract ownership

Every endpoint above is mirrored by a Zod schema in `mobile/src/lib/schemas`
(for forms) and a TypeScript type in `mobile/src/api/types.ts` /
`admin-dashboard/src/api/types.ts`. Changing a response shape means changing
three files in one commit — that is the API contract discipline (§26.9).
