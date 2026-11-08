# 5. Development Roadmap, Progress Checklist & Risks

> **Rule (§26):** one phase at a time, the app stays runnable after every phase,
> errors are fixed before moving on.

---

## 5.1 Phase plan with concrete deliverables

### ✅ PHASE 1 — Project foundation, architecture & database design
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Monorepo structure (`mobile/`, `admin-dashboard/`, `backend/`, `database/`, `documentation/`) | `/` | ✅ |
| 2 | Architecture, DB design, API contracts, user journeys, risk docs | `documentation/` | ✅ |
| 3 | FastAPI app: settings, logging, error envelope, CORS, request-id, health/meta | `backend/app` | ✅ |
| 4 | **Complete ORM design** — 18 tables, FKs, unique/check constraints, partial unique indexes, soft delete | `backend/app/models` | ✅ |
| 5 | Alembic environment + initial migration (works on PostgreSQL & SQLite) | `backend/alembic` | ✅ |
| 6 | Prisma reference schema mirroring the models | `database/schema.prisma` | ✅ |
| 7 | Admin bootstrap from env (hashed, idempotent, non-destructive) | `backend/app/services/admin_bootstrap.py` | ✅ |
| 8 | Security primitives: Argon2id, access JWT, hashed refresh tokens | `backend/app/core/security.py` | ✅ |
| 9 | Development seed script (10 users, 6 vehicles, 8 rides, 1 matched trip + chat, 1 completed trip + reviews, 1 report) | `backend/scripts/seed.py` | ✅ |
| 10 | Pytest suite: system + security + config + bootstrap + **DB constraint/concurrency** tests | `backend/tests` | ✅ (31 passing) |
| 11 | Docker Compose (PostgreSQL + API) with Dockerfile | `/docker-compose.yml` | ✅ |
| 12 | `.env.example` for backend + repository `.gitignore` | `backend/.env.example` | ✅ |
| 13 | Expo project scaffold (config, theme, navigation shell) | `mobile/` | ✅ scaffold |
| 14 | Vite + React + Tailwind admin scaffold (auth shell, sidebar layout) | `admin-dashboard/` | ✅ scaffold |

### ✅ PHASE 2 — Authentication, roles & university verification
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Register / login / refresh / logout / logout-all / forgot / reset / verify-email / change-password / resend-verification | `backend/app/api/v1/auth.py` | ✅ |
| 2 | Argon2id hashing, access JWT, **rotating** refresh tokens (SHA-256 at rest) with reuse detection | `backend/app/services/auth_service.py`, `core/security.py` | ✅ |
| 3 | Auth dependencies `get_current_user`, `get_optional_user`, `require_verified_user`, `require_admin` | `backend/app/api/deps.py` | ✅ |
| 4 | Suspended/deactivated account blocking, `last_login_at`, silent re-hash on login | `auth_service.authenticate` | ✅ |
| 5 | Auto-verification for trusted university domains + manual ID submission queue | `auth_service.register_user`, `submit_verification` | ✅ |
| 6 | Email delivery with SMTP + development console backend, single-use hashed tokens | `backend/app/services/email_service.py`, migration `550e18b493a6` | ✅ |
| 7 | Profile read/update, public profile with privacy allow-list, reviews list, block/unblock | `backend/app/api/v1/users.py` | ✅ |
| 8 | Rate limiting on login/register/reset/forgot with the shared error envelope | `backend/app/core/rate_limit.py` | ✅ |
| 9 | Mobile: keystore session, single-flight refresh interceptor, auth gate, Onboarding → Login → Signup → Forgot + verification modal + 5-tab shell + real Profile | `mobile/app`, `mobile/src` | ✅ |
| 10 | Admin: real login, `ProtectedRoute` (token → `/auth/me` → role), session store, live sidebar identity + logout | `admin-dashboard/src` | ✅ |
| 11 | 38 automated auth tests | `backend/tests/test_auth.py` | ✅ |

---

### 🔜 PHASE 2 (original scope, kept for reference) — Authentication, roles & verification
- `app/schemas/auth.py`, `app/services/auth_service.py`, `app/api/deps.py`
- `POST /auth/register|login|refresh|logout|forgot-password|reset-password|verify-email`, `GET /auth/me`
- Argon2 hashing wired end-to-end, refresh-token rotation + reuse detection
- Role guard dependencies (`require_user`, `require_verified`, `require_admin`)
- Suspended-account blocking, `last_login_at` tracking
- Manual verification submission + status endpoint
- Mobile: Splash → Onboarding → Login/Signup/Forgot (React Hook Form + Zod), token
  stored in `expo-secure-store`, auto-refresh axios interceptor, auth gate in Expo Router
- Admin: real login + protected routes
- Tests: signup duplicate email, weak password, wrong password, expired token,
  refresh rotation, suspended login, reset-password flow

### ✅ PHASE 3 — Core ride system (vehicles → publish → explore → request → accept)
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Vehicle CRUD: PENDING on create/edit, one primary per member, unique plate, delete blocked while on an open ride | `backend/app/api/v1/vehicles.py`, `services/vehicle_service.py` | ✅ |
| 2 | Ride publish with campus end forced to SSUET, `seats_remaining = 1`, FREE vs SHARE_FUEL validation | `backend/app/api/v1/rides.py`, `services/ride_service.py` | ✅ |
| 3 | Explore feed: direction, vehicle type, fuel preference, area search, departure window, radius (lat/lng), cursor pagination over `(departure_at, id)` | `services/ride_service.py` | ✅ |
| 4 | Ride detail with privacy projection — exact points & phone only for driver, accepted passenger, admin | `schemas/ride.py`, `api/v1/rides.py` | ✅ |
| 5 | Request lifecycle: create (verified only, no self-request, no duplicate), withdraw, driver inbox, reject with note | `backend/app/api/v1/requests.py`, `services/request_service.py` | ✅ |
| 6 | **Atomic seat claim** on accept: `with_for_update()` ride lock → in-transaction status/seat check → partial unique index `uq_trips_one_active_per_ride`; `IntegrityError` → 409 `RIDE_NOT_AVAILABLE` | `services/request_service.py` | ✅ |
| 7 | Accept side-effects: ride `MATCHED` / `seats_remaining 0` / `matched_at`, request `ACCEPTED`, other pending requests auto-`REJECTED`, `Conversation` created, notifications to both sides | `services/request_service.py` | ✅ |
| 8 | Mobile data layer: typed `src/api/rides.ts` (rides, requests, vehicles) + TanStack Query keys | `mobile/src/api/rides.ts` | ✅ |
| 9 | Mobile Publish wizard — 5 steps (direction → area/pin → date & time → vehicle → fare & note) with review card | `mobile/app/(tabs)/publish.tsx` | ✅ |
| 10 | Mobile Explore feed: direction toggle, area search, fare/vehicle filters, skeleton, empty & error states, load-more cursor | `mobile/app/(tabs)/explore.tsx`, `src/components/RideCard.tsx`, `src/components/Skeleton.tsx` | ✅ |
| 11 | Mobile ride detail with `can_request` gating, request sheet, driver cancel, meeting-point reveal after match | `mobile/app/ride/[id].tsx` | ✅ |
| 12 | Mobile My Rides (Published / Requested / Upcoming / Completed / Cancelled) with driver accept & reject inbox | `mobile/app/(tabs)/my-rides.tsx` | ✅ |
| 13 | Mobile vehicle registration + verification status | `mobile/app/vehicles.tsx` | ✅ |
| 14 | Google Maps: `expo-location` + `react-native-maps` installed, area centroid fallback, graceful degradation without a key | `src/components/LocationPicker.tsx`, `src/lib/areas.ts` | ✅ |
| 15 | Home screen now renders real journeys from the API (no placeholder cards) | `mobile/app/(tabs)/index.tsx` | ✅ |
| 16 | 60 new backend tests (8 vehicles + 33 rides + 19 requests) incl. 4-thread race for the last seat | `backend/tests/test_rides.py`, `test_requests.py`, `test_vehicles.py` | ✅ (**129 total passing**) |

> Phase 3 mobile note: `My Rides → Upcoming/Completed` were filled by Phase 4, which
> replaced them with real trips (see the Phase 4 table below).

### ✅ PHASE 4 — Trip lifecycle (start → complete → cancel / no-show)
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Trip service with the full state machine and transition guards | `backend/app/services/trip_service.py` | ✅ |
| 2 | `GET /trips/mine` (role / status / upcoming filters) + `GET /trips/{id}` | `backend/app/api/v1/trips.py` | ✅ |
| 3 | `POST /trips/{id}/start` — driver-only, −6 h/+12 h window, ride → `IN_PROGRESS` | `trip_service.start_trip` | ✅ |
| 4 | `POST /trips/{id}/complete` — per-side confirmation, both required; counters + ride `COMPLETED` | `trip_service.complete_trip` | ✅ |
| 5 | `POST /trips/{id}/cancel` — passenger reopens the seat, driver cancels the ride; reasons + notifications | `trip_service.cancel_trip` | ✅ |
| 6 | `POST /trips/{id}/no-show` — driver-only, seat freed before departure, ride closed after it | `trip_service.mark_no_show` | ✅ |
| 7 | Viewer-specific action flags on every trip payload (`can_start`, `awaiting_my_confirmation`, …) | `backend/app/schemas/trip.py` | ✅ |
| 8 | Housekeeping: `expire_stale_rides` + `auto_complete_stale_trips` (service, CLI, in-process scheduler flag) | `services/maintenance_service.py`, `scripts/expire_stale_rides.py`, `MAINTENANCE_INTERVAL_MINUTES` | ✅ |
| 9 | New notification templates `TRIP_STARTED`, `TRIP_AWAITING_CONFIRMATION`, `TRIP_NO_SHOW`; richer `TRIP_COMPLETED` | `services/notification_service.py` | ✅ |
| 10 | Ride payload exposes `my_trip_id`; `/requests/{id}/accept` reuses the shared trip serializer | `schemas/ride.py`, `services/ride_service.py`, `api/v1/requests.py` | ✅ |
| 11 | Mobile: typed trip client, `TripCard`, trip detail with call + completion + cancel/no-show | `mobile/src/api/trips.ts`, `src/components/TripCard.tsx`, `app/trip/[id].tsx` | ✅ |
| 12 | Mobile: My Rides Upcoming / Completed / Cancelled now driven by real trips; ride detail "Open trip" | `mobile/app/(tabs)/my-rides.tsx`, `app/ride/[id].tsx` | ✅ |
| 13 | 35 trip tests incl. seat reuse after passenger cancel, double-confirmation, all maintenance branches | `backend/tests/test_trips.py` | ✅ (**164 total passing**) |

### ✅ PHASE 5 — Trip chat & notifications
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Conversation model wired end-to-end (created on accept), participant-only access | `backend/app/services/chat_service.py` | ✅ |
| 2 | REST chat: list conversations, detail, history with backwards cursor, send, mark-read | `backend/app/api/v1/chat.py` | ✅ |
| 3 | WebSocket `/chat/ws/{conversation_id}` — JWT handshake (query or header), room validation, 1008 refusal | `app/api/v1/chat.py`, `app/services/chat_hub.py` | ✅ |
| 4 | Live frames: message, typing, read receipt, presence, error, ping/pong — documented envelope | `app/schemas/chat.py` | ✅ |
| 5 | Per-viewer `is_mine` delivery, exact message ordering, blocked-pair and cancelled-trip guards | `chat_service`, `api/v1/chat.py` | ✅ |
| 6 | Notification API: list/unread-only/cursor, unread count, mark one/all, device CRUD | `backend/app/api/v1/notifications.py` | ✅ |
| 7 | Expo push: post-commit queue + flush, batching, `DeviceNotRegistered` cleanup, network-failure resilience | `backend/app/services/push_service.py` | ✅ |
| 8 | Mobile chat screen with optimistic send, reconnect/backoff, typing, presence, read receipts, REST fallback | `mobile/app/chat/[id].tsx`, `src/api/chat.ts` | ✅ |
| 9 | Mobile messages list + notifications screen with deep links and unread badge on Home | `mobile/app/chats.tsx`, `app/notifications.tsx`, `app/(tabs)/index.tsx` | ✅ |
| 10 | Push registration lifecycle (on sign-in / release on sign-out) + `expo-notifications` installed | `mobile/src/lib/push.ts`, `app/_layout.tsx`, `app.config.ts` | ✅ |
| 11 | 38 new backend tests (22 chat incl. socket protocol, 16 notifications/push) | `backend/tests/test_chat.py`, `test_notifications.py` | ✅ (**202 total passing**) |

### ✅ PHASE 6 — Admin dashboard
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Admin schemas: `Page[T]` envelope, dashboard/analytics aggregates, per-entity rows, dossier, action log, settings | `backend/app/schemas/admin.py` | ✅ |
| 2 | Admin service: every query + mutation, `AdminAction` audit row and member notification on each decision | `backend/app/services/admin_service.py` | ✅ |
| 3 | 20 guarded routes (`AdminUser` re-checks role + account status from the DB, not the token) | `backend/app/api/v1/admin.py` | ✅ |
| 4 | Dashboard aggregates: member/verification/vehicle/suspension counters, rides/trips today, status breakdowns, 14-day series | `GET /admin/dashboard` | ✅ |
| 5 | Analytics: growth series, completion & cancellation rate, average rating, fuel/vehicle/direction splits, top areas | `GET /admin/analytics` | ✅ |
| 6 | User management: search + role/status/verification filters, dossier drawer, verify/reject/suspend/reactivate | `pages/Users.tsx` | ✅ |
| 7 | Verification & vehicle queues with reason-mandatory rejection | `pages/Verifications.tsx`, `pages/Vehicles.tsx` | ✅ |
| 8 | Ride oversight with force-cancel (cascades to trips + notifies both members) and trip views | `pages/Rides.tsx`, `pages/Trips.tsx` | ✅ |
| 9 | Complaint workflow (under review / resolve / dismiss with note) and suspended-account reactivation | `pages/Reports.tsx`, `pages/Suspended.tsx` | ✅ |
| 10 | Recharts dashboard + analytics, read-only settings screen, honest 404, sidebar §16 structure without phase badges | `pages/Dashboard.tsx`, `Analytics.tsx`, `Settings.tsx`, `NotFound.tsx` | ✅ |
| 11 | 38 new backend tests (guards, decisions, queues, filters, cascade, audit log, secret leakage) | `backend/tests/test_admin.py` | ✅ (**240 total passing**) |
| 12 | Live verification against the dev database + `tsc` clean + `npm run build` | `documentation/10-phase6-admin-dashboard.md` | ✅ |

### ✅ PHASE 7 — Trust & quality
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Review contracts: 1–5 + optional comment, page with average and 5-star breakdown, pending list | `backend/app/schemas/review.py` | ✅ |
| 2 | Review service: completed trips only, participants only, one per side, recomputed aggregates, `NEW_REVIEW` notification | `backend/app/services/review_service.py` | ✅ |
| 3 | `POST /reviews/trips/{id}`, `GET /reviews/pending`, `/reviews/me/received`, `/reviews/users/{id}` (10/min) | `backend/app/api/v1/reviews.py` | ✅ |
| 4 | Report contracts + service: derived subject, trip/ride membership proof, self-report and duplicate-open guards | `schemas/report.py`, `services/report_service.py` | ✅ |
| 5 | `POST /reports`, `GET /reports`, `GET /reports/{id}` (5/min) + acknowledgement and admin fan-out | `backend/app/api/v1/reports.py` | ✅ |
| 6 | Office decision reaches the reporter (`REPORT_RESOLVED` + note) | `admin_service.update_report` | ✅ |
| 7 | Review moderation: `GET /admin/reviews`, `POST /admin/reviews/{id}/hide|unhide`, audited, average recomputed | `admin_service`, `api/v1/admin.py` | ✅ |
| 8 | 25 review tests + 20 report/blocking tests + 19 privacy & IDOR tests | `tests/test_reviews.py`, `test_reports.py`, `test_security.py` | ✅ (**304 total passing**) |
| 9 | Mobile: rate-trip modal, report modal, my ratings, my reports, blocked members, trip + home + profile wiring | `mobile/app/review/[tripId].tsx`, `app/report/[tripId].tsx`, `app/{reviews,my-reports,blocked}.tsx` | ✅ |
| 10 | Console: Reviews & ratings tab with hide/restore and reason dialog | `admin-dashboard/src/pages/Reports.tsx` | ✅ |
| 11 | Live end-to-end verification + `expo export` 4.18 MB + docs `11` | `documentation/11-phase7-trust-quality.md` | ✅ |

### ✅ PHASE 8 — Final testing & deployment
| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | 10 end-to-end journey tests across every phase (happy path, seat reuse, cancellation, no-show, verification gate, vehicle policy, housekeeping, safety→suspension, unread counts) | `backend/tests/test_journeys.py` | ✅ |
| 2 | Coverage measurement and report — **94%** of 4,187 statements | `documentation/testing/coverage.txt` | ✅ |
| 3 | Load sanity script + recorded results (7 endpoints, 400 req each, 20 concurrent, 0 errors) | `backend/scripts/load_check.py`, `documentation/testing/load-sanity.txt` | ✅ |
| 4 | Release version bump to **1.0.0**, versionCode/autoIncrement wired, EAS `development`/`preview`(APK)/`production`(AAB) profiles verified | `mobile/app.config.ts`, `eas.json`, `package.json` | ✅ |
| 5 | Icon / adaptive icon / splash / favicon verified at the sizes Expo expects | `mobile/assets/` | ✅ |
| 6 | `expo config` resolution, `tsc --noEmit`, `expo export --platform android` (4.18 MB) | mobile | ✅ |
| 7 | Testing & release documentation incl. the physical-device checklist and stated limitations | `documentation/12-phase8-testing-and-release.md` | ✅ |
| 8 | Admin operations runbook (queues, incidents, metrics, health, configuration, handover) | `documentation/13-admin-runbook.md` | ✅ |
| 9 | README rewritten with release steps and verified numbers; contract/risk docs aligned | `README.md` | ✅ |

---

## 5.2 Live progress board

| Area | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 | Phase 7 | Phase 8 |
|---|---|---|---|---|---|---|---|---|
| Backend | ✅ | ✅ | ✅ vehicles/rides/requests | ✅ trip lifecycle + jobs | ✅ chat + notifications/push | ✅ admin API (20 routes) | ✅ reviews + reports + hardening | ✅ journeys + load sanity |
| Database | ✅ | ✅ | ✅ (no migration needed) | ✅ (no migration needed) | ✅ (no migration needed) | ✅ (no migration needed) | ✅ (no migration needed) | ✅ (no migration needed) |
| Mobile | 🟡 scaffold | ✅ auth + shell | ✅ explore/publish/request | ✅ trips + My Rides | ✅ chat + notifications | — | ✅ reviews/reports/blocking | ✅ v1.0.0 release config |
| Admin | 🟡 scaffold | ✅ login + guard | — | — | — | ✅ 11 modules on real data | ✅ review moderation tab | ✅ build verified |
| Tests | ✅ 31 | ✅ 69 total | ✅ 129 total | ✅ 164 total | ✅ 202 total | ✅ 240 total | ✅ 304 total | ✅ **314 total · 94%** |
| Docs | ✅ | ✅ | ✅ `07` | ✅ `08` | ✅ `09` | ✅ `10` | ✅ `11` | ✅ `12` + `13` + `14` |

Legend: ✅ done · 🟡 scaffolded · ⬜ pending · — not applicable

---

## 5.3 Definition of done (per phase)

1. `pytest` green, no skipped business-rule tests.
2. `alembic check` reports no pending model changes.
3. Every new endpoint appears in Swagger with request/response examples.
4. Every new screen has loading, empty and error states.
5. No secret, URL or key hardcoded; `.env.example` updated.
6. `documentation/progress` board and README updated.
7. The app boots from a clean clone with the documented commands.

---

## 5.4 Phase 1 verification log (evidence)

Every item below was executed in a clean environment at the end of Phase 1.

| Check | Command | Result |
|---|---|---|
| Backend boots | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `Application startup complete`, listening on :8000 |
| Liveness | `curl localhost:8000/api/v1/health` | `{"status":"ok","version":"0.1.0","environment":"development"}` |
| Readiness | `curl localhost:8000/api/v1/health/ready` | `{"status":"ready","database":"ok"}` |
| Client bootstrap | `curl localhost:8000/api/v1/meta` | university coords + `max_confirmed_passengers: 1` + `maps_configured: false` |
| Swagger UI | `GET /docs` | `200` |
| Models registered | `len(Base.metadata.tables)` | `18` |
| Migration applies | `alembic upgrade head` (SQLite **and** PostgreSQL offline render) | 19 tables created; partial unique indexes present in PostgreSQL DDL |
| Seed data | `python -m scripts.seed --reset` | 10 users · 6 vehicles · 8 open rides · 1 matched trip + 3 messages · 1 completed trip + 2 reviews · 1 report |
| Test suite | `python -m pytest` | **31 passed** |
| Admin bootstrap | first boot | `Bootstrap admin created: admin@example.com`, stored as `$argon2id$v=19$m=65536…` (97 chars), no plaintext |
| Admin bootstrap idempotency | second boot | `Admin bootstrap skipped: account … already exists (password untouched)` |
| Admin dashboard build | `npx tsc --noEmit && npm run build` | typecheck clean, `✓ built` (273 kB / 91 kB gzip) |
| Admin ↔ API proxy | `curl localhost:5173/api/v1/meta` | same JSON as direct call (Vite proxy works) |

**Not verifiable in this environment (owner actions):** physical Android device run
of the Expo app, EAS cloud build, real Google Maps keys, PostgreSQL server
(docker-compose path was validated through Alembic's offline PostgreSQL SQL
render only). All are documented in `06-risks-and-external-setup.md`.


---

## 5.5 Phase 2 verification log (evidence)

| Check | Command | Result |
|---|---|---|
| Register (trusted domain) | `POST /api/v1/auth/register` | `201`, token pair, `verification_status=VERIFIED`, student profile created |
| Register outside domain | same, `@gmail.com` | `201`, `verification_status=UNVERIFIED` |
| Duplicate email / phone / university ID | same | `422` with field-level `details` (`already registered`) |
| Weak passwords (`short1`, `lettersonly`, `12345678901`, `password1`) | same | `422` with a human-readable reason |
| Self-registering an ADMIN | `role=ADMIN` | `422` (rejected by schema) |
| Login | `POST /api/v1/auth/login` (seeded `ali@ssuet.edu.pk`) | `200`, access len 287, refresh len 64, `expires_in` 1800 |
| Wrong password vs unknown email | both | identical `401 {"code":"UNAUTHORIZED","message":"Incorrect email or password."}` |
| Suspended account | seeded `usman@ssuet.edu.pk` | `403` + `reason_code=ACCOUNT_SUSPENDED` |
| Refresh rotation | `/auth/refresh` | new pair issued; old token now `401` |
| Reuse / theft detection | replay consumed token | `401 "This session was already used"` **and** the rotated token is revoked too |
| `GET /auth/me` without/with token | — | `401` / `200` with phone + university ID (owner view) |
| Public profile privacy | `/users/{id}/public` | contains no `email`, `phone`, `university_id`, `home_area`, `suspension_reason` |
| Privilege escalation attempt | `PATCH /users/me` with `role=ADMIN`, `completed_trips_count=999` | ignored — role stays `STUDENT`, counters unchanged |
| Password reset | full flow with captured token | old password `401`, new password `200`, token single-use, existing sessions revoked |
| Verification submission | `POST /users/me/verification` | `201` `PENDING`; duplicate attempt `422`; verified account `422` |
| Rate limiting | 12 rapid failed logins | `429` with the standard envelope |
| Swagger surface | `GET /openapi.json` | 21 paths under `/api/v1` |
| Models vs migrations | `alembic check` | "No new upgrade operations detected" |
| Full test suite | `python -m pytest` | **69 passed** |
| Mobile typecheck | `npx tsc --noEmit` (real `node_modules`, 842 packages) | clean |
| Expo config | `npx expo config --type public` | valid: `com.ssuet.rideshare`, permissions, splash `#0B1F3A`, `extra.apiUrl` |
| Admin build | `npx tsc --noEmit && npm run build` | clean, 282 kB / 94 kB gzip |
| Admin guard | route `/` without session | redirects to `/login`; non-ADMIN token is refused client- and server-side |

**Owner actions still required:** SMTP credentials for real verification emails
(until then links are written to the backend log), and a physical Android run of
the Expo app (`npx expo start --android`). Mobile typechecking was performed
against installed packages, but no emulator/device is available in this sandbox.

---

## 5.6 Post-roadmap: release-candidate audit (v1.0.0)

The roadmap ends at Phase 8. Before calling v1.0.0 done, the repository was audited as a stranger
would receive it. Full evidence: [`14-release-candidate-audit.md`](14-release-candidate-audit.md).

| Item | Command | Result |
| --- | --- | --- |
| API ↔ docs | `cd backend && python -m scripts.check_contracts` | 89 implemented / 87 documented · ✓ exit 0 |
| Clean-room boot | `DATABASE_URL=…alembic upgrade head; python -m scripts.seed` + HTTP smoke | 14/14 checks on a brand-new database |
| Secrets | regex scan for provider keys, PEM blocks, committed `.env`/`*.db` | none found |
| Docker context | review of `backend/Dockerfile` + compose | `backend/.dockerignore` added (was copying `.venv`, `*.db`, `.env`) |
| Mobile copy | `grep -rn "Phase [0-9]" mobile/app mobile/src` | no stale phase promises; 4 strings corrected |
| Admin console | Playwright sweep of all 12 destinations | 0 console errors, 0 responses ≥ 400, `/does-not-exist` → Page not found |
| Mobile/adm in types | `tsc --noEmit` in both apps | clean |

**Verdict:** release candidate accepted; no open defects. Remaining gaps are the documented
limitations (cash settlement, pasted-link verification, optional Maps/SMTP/push keys, single
confirmed passenger), recorded in doc 12 §8 and doc 14 §6.

---

## 5.7 Phase 9 — media upload pipeline (post-roadmap extension)

Requested continuation after the v1.0.0 audit. Removes the largest documented
limitation: verification documents were previously a pasted external link.
Full detail and evidence: [`15-phase9-media-pipeline.md`](15-phase9-media-pipeline.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | `media_assets` table + `verifications.document_asset_id`, migration `0ff2be74d4a7` (up/down verified, `alembic check` clean) | `app/models/media.py`, `alembic/versions/` | ✅ |
| 2 | Upload service: magic-byte sniffing, chunked 5 MB cap, generated storage paths, SHA-256, sanitised display names | `app/services/media_service.py` | ✅ |
| 3 | `POST /uploads/verification`, `GET /media/{id}`, `DELETE /media/{id}` — owner/admin authorisation, no public mount | `app/api/v1/uploads.py` | ✅ |
| 4 | Verification submission accepts an upload **or** a link (exactly one), foreign asset ids are 404 | `app/schemas/user.py`, `app/services/auth_service.py` | ✅ |
| 5 | Mobile: photo picker (library + camera), inline preview, 5 MB pre-check, upload-then-submit, withdraw | `mobile/app/verification.tsx`, `src/api/auth.ts`, `expo-image-picker` | ✅ |
| 6 | Admin console: **View upload** fetches the file with the admin token and opens a blob tab; legacy links still work | `admin-dashboard/src/lib/media.ts`, `src/pages/Verifications.tsx` | ✅ |
| 7 | 24 new tests; suite **338 passed**, coverage **94 %** of 4,392 statements | `tests/test_uploads.py`, `documentation/testing/coverage.txt` | ✅ |
| 8 | Live evidence: 11-step HTTP run (upload → reject → submit → 403 for stranger → admin read → approve → withdraw) and a Playwright check of the console viewer | doc 15 §5, `screenshots/phase9-verification-queue.png` | ✅ |
| 9 | Docs: contract table §3.10b, runbook §8 (storage/backup/retention), risks R15/R16, `.env.example`, README, this roadmap | `documentation/`, `README.md` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Unit/feature suite | `python -m pytest` | **338 passed** (112 s) |
| New module coverage | `pytest --cov=app` | media model/schema 100 %, service 93 %, routes 88 % |
| Migrations | `alembic upgrade head` → `downgrade -1` → `upgrade head`, `alembic check` | round-trip clean, "No new upgrade operations detected" |
| API ↔ docs | `python -m scripts.check_contracts` | **92 implemented / 92 documented**, exit 0 |
| Mobile | `npx tsc --noEmit` | clean (with `expo-image-picker@~17.0.11`) |
| Admin | `npx tsc --noEmit && npm run build` | clean, built in 4.84 s |
| Browser | Playwright: login → Verification Requests → **View upload** | popup `blob:` tab, image decoded, 0 console errors |

---

## 5.8 Phase 10 — vehicle documents & media housekeeping (post-roadmap extension)

Follows Phase 9: the same upload pipeline, applied to vehicles, plus the orphan sweep
Phase 9 listed as missing. Detail and evidence: [`16-phase10-vehicle-documents.md`](16-phase10-vehicle-documents.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | `vehicles.photo_asset_id` / `registration_asset_id`, migration `1ecaa4a7e72e` (up/down verified, `alembic check` clean) | `app/models/vehicle.py`, `alembic/versions/` | ✅ |
| 2 | `POST /uploads/vehicle` with purpose `VEHICLE_DOCUMENT` | `app/api/v1/uploads.py` | ✅ |
| 3 | Vehicle create/update accept the ids; owner + purpose enforced (404 / 422) | `app/services/vehicle_service.py` | ✅ |
| 4 | Orphan sweep with retention window + dry run, folded into the housekeeping run | `app/services/media_service.py`, `maintenance_service.py`, `scripts/sweep_media.py` | ✅ |
| 5 | `GET /admin/media` storage overview (files, bytes, orphans, oldest, limits) | `app/api/v1/admin.py` | ✅ |
| 6 | Mobile vehicle form: attach photo + registration book, upload immediately, replace cleanly | `mobile/app/vehicles.tsx`, `src/api/media.ts` | ✅ |
| 7 | Console **Proof** column streams both documents with the admin token | `admin-dashboard/src/pages/Vehicles.tsx`, `src/lib/media.ts` | ✅ |
| 8 | 15 new tests → suite **353 passed**, coverage **94 %** of 4,511 statements | `tests/test_media_housekeeping.py` | ✅ |
| 9 | Docs: contract §3.10b, runbook §8, risks R16, `.env.example`, README, this roadmap | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Suite | `python -m pytest` | **353 passed** (98 s) |
| Migrations | `alembic upgrade head` → `downgrade -1` → `upgrade head`, `alembic check` | round-trip clean |
| API ↔ docs | `python -m scripts.check_contracts` | **94 implemented / 94 documented**, exit 0 |
| Live HTTP | 11-step vehicle + sweep run (doc 16 §5) | 11/11 |
| Sweep CLI | `--stats`, `--dry-run`, real run | 4 files/1 orphan → dry run keeps it → real run deletes it → 3 files/0 orphans |
| Mobile | `npx tsc --noEmit` | clean |
| Admin | `npx tsc --noEmit && npm run build` | clean (5.23 s) |
| Browser | Playwright: Vehicle verification → Proof → Registration book | `blob:` tab with the image, 0 console errors |

---

## 5.9 Phase 11 — production deployment & CI (post-roadmap extension)

Turns "runs on my laptop" into "runs as a service": supervisor, TLS proxy, backups, a
smoke test a non-developer can run, PostgreSQL parity and a CI pipeline. Detail and
evidence: [`17-production-deployment.md`](17-production-deployment.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | Production environment contract (secrets, DB, media, rate limits) | `deploy/env.production.example` | ✅ |
| 2 | systemd unit: gunicorn + uvicorn workers, hardened, `ReadWritePaths` = media | `deploy/ssuet-api.service` | ✅ |
| 3 | nginx: TLS, HSTS/CSP, one origin for console + API + uploads, WebSocket upgrade, 6 MB cap, edge rate limits with `limit_req_status 429` | `deploy/nginx/ssuet-rideshare.conf` | ✅ |
| 4 | Backup / restore with manifest, checksums and retention (DB **and** media) | `deploy/backup.sh`, `deploy/restore.sh` | ✅ |
| 5 | Post-deploy smoke test (17 checks) | `deploy/smoke.sh` | ✅ |
| 6 | PostgreSQL parity: suite + `alembic check` + seeded boot; `TEST_DATABASE_URL` honoured by conftest | `tests/conftest.py` | ✅ |
| 7 | CI: 5 jobs (sqlite+coverage gate, postgres+migrations, contract audit, admin, mobile export) | `.github/workflows/ci.yml` | ✅ |
| 8 | Production dependency set | `backend/requirements-prod.txt` | ✅ |
| 9 | Deployment doc with the handover checklist (§7) | `documentation/17-production-deployment.md` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| nginx config | `nginx -t` with the shipped file | syntax ok, requests served over TLS |
| Smoke test | `./deploy/smoke.sh https://rideshare.ssuet.edu.pk` | **17 passed, 0 failed** |
| WebSocket | `wss://…/api/v1/chat/ws/{id}` via 3 workers | ready → message → persisted → readable over REST |
| Upload cap | 7 MB POST through the proxy | **413** at the edge |
| Edge rate limit | 14 logins in a burst | **429** |
| Backup + restore | `backup.sh`, checksum verify, `diff -r` of restored media | identical; DB readable (13 users) |
| PostgreSQL suite | `TEST_DATABASE_URL=… python -m pytest` | **353 passed** (154 s) |
| PostgreSQL boot | seed + API on PG | 6/6 (health, ready, login, explore, admin, dashboard) |
| CI rehearsal | every workflow step run locally | compileall ✓ · coverage gate 93.99 % ✓ · migrations round-trip ✓ · contract 94/94 ✓ |

---

## 5.10 Phase 12 — observability & load validation (post-roadmap extension)

Makes the deployed service answer "is anything wrong?" without an SSH session, and
replaces the Phase 8 SQLite figures with measurements from the production stack.
Detail: [`18-observability-and-load.md`](18-observability-and-load.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | Request correlation: `X-Request-ID` echo/generate, timing headers, configurable slow-request logging | `app/main.py`, `SLOW_REQUEST_MS` | ✅ |
| 2 | `GET /admin/health`: DB latency/dialect/schema revision vs head/pool, queues, media + disk, housekeeping, `warnings[]` | `app/services/system_service.py` | ✅ |
| 3 | Process facts (uptime, last housekeeping run) | `app/core/runtime.py` | ✅ |
| 4 | `deploy/monitor.sh` (5 checks, exit 0/1/2, optional webhook) + systemd timer | `deploy/` | ✅ |
| 5 | Load tool can measure the real stack (`--insecure`), reports p50/p95/p99 + errors | `scripts/load_check.py` | ✅ |
| 6 | Measured capacity on PostgreSQL + gunicorn + nginx; concurrency sweep, proxy overhead, worker-count comparison | `documentation/testing/load-postgres.txt` | ✅ |
| 7 | 12 new tests (correlation + panel, incl. stale-schema and slow-DB warnings) → **365 passed**, 94 % | `tests/test_observability.py` | ✅ |
| 8 | Docs: contract §3.10c, runbook §6a, README, this roadmap | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Suite | `python -m pytest` | **365 passed** (99 s) |
| Contract | `python -m scripts.check_contracts` | 95 / 95, exit 0 |
| Health panel (live, production stack) | `GET /admin/health` via nginx | DB 0.15 ms, revision == head, queues correct, disk reported, `warnings: []` |
| Monitor healthy | `./deploy/monitor.sh` | 5 OK, exit 0 |
| Monitor failing | API stopped | 2 FAIL, exit 2, webhook delivered to a local sink |
| Load, Explore | 200 requests @ 20 concurrent, direct | 146.6 rps · p50 123 ms · p95 232 ms · **0 errors** |
| Concurrency sweep | 1 → 40 concurrent | 13 → 116 ms p50, plateau ~145–150 rps |
| Proxy overhead | nginx vs direct @ concurrency 3 | +3.2 to +6.7 ms |
| PostgreSQL parity | `TEST_DATABASE_URL=… pytest` | 365 passed |

---

## 5.11 Phase 13 — profile photos (post-roadmap extension)

The last field that was "a URL somebody typed" becomes a real upload, with a visibility
rule that is the opposite of an ID card's. Detail:
[`19-profile-photos.md`](19-profile-photos.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | `users.profile_photo_asset_id` → `media_assets.id` (`ON DELETE SET NULL`), constraint deferred with `use_alter` to break the users↔media cycle | migration `9d31c4f8a2b7` | ✅ |
| 2 | `POST /users/me/photo` — magic-number validation, images only, `MAX_PROFILE_PHOTO_BYTES` 2 MB, 10/min | `app/api/v1/users.py` | ✅ |
| 3 | `DELETE /users/me/photo` — removes row + file, keeps the legacy link | same | ✅ |
| 4 | `GET /users/{id}/photo` — any **authenticated** member; ETag + private cache; anonymous 401 | same | ✅ |
| 5 | Replacing a photo deletes the previous file at once; the sweep knows avatars as a third reference set | `media_service` | ✅ |
| 6 | `User.photo_url` fills every existing `profile_photo_url` field: rides, public profiles, chats, trips, reviews, reports, requests, admin list | services | ✅ |
| 7 | Mobile `<Avatar>` renders the photo with the bearer token; profile screen gains a picker ("Add/Change/Remove photo") | `mobile/` | ✅ |
| 8 | Console: avatar column + dossier avatar, fetched as a blob with the token, cached per URL | `admin-dashboard/` | ✅ |
| 9 | 22 tests (upload/replace/delete, visibility boundary, validation, sweep, payload reach) → **387 passed**, 94 % | `tests/test_profile_photos.py` | ✅ |
| 10 | Docs: contract §3.4, README, runbook, this roadmap | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Suite | `python -m pytest` | **387 passed** (103 s) |
| PostgreSQL parity | `TEST_DATABASE_URL=… pytest` | **387 passed** (160 s) |
| Migrations | `alembic upgrade head` · `alembic check` | applied on SQLite + PostgreSQL; "No new upgrade operations detected." |
| Contract | `python -m scripts.check_contracts` | 98 / 98, exit 0 |
| Live upload → another member's read | nginx + TLS + production env | 201 · 200 · bytes identical · 401 anonymous |
| Explore payload | `GET /rides` | 3 of 7 driver cards carry a photo |
| Console | Playwright over https | 14 rows · 4 photos decoded · 10 initials · 0 console errors |
| Smoke | `./deploy/smoke.sh` | **17 / 17** (incl. the new 401 check) |
| Mobile | `npx tsc --noEmit` · `expo export -p android` | clean · 4,204,699 B bundle |
| Admin | `npm run build` | 796 K dist |

---

## 5.12 Phase 14 — image normalisation (post-roadmap extension)

Closes the two real risks Phase 13 introduced: GPS metadata in a picture that every
member can read, and megabytes of image data served into a 40-pixel circle. Detail:
[`20-image-normalisation.md`](20-image-normalisation.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | Decode → pixel-budget check → EXIF orientation applied → square centre crop → 512 px → WebP re-encode (metadata gone) | `app/services/image_service.py` | ✅ |
| 2 | Decompression-bomb refusal **before** decoding (40 MP ceiling + Pillow guard) and clean rejection of corrupt images | same | ✅ |
| 3 | `store_upload(normalise=True)` collects the bytes in memory and writes only the processed result — the original never reaches disk | `media_service` | ✅ |
| 4 | `GET /users/{id}/photo?size=thumb` — 128 px variant, own ETag, in-process LRU (+ client cache) | `app/api/v1/users.py` | ✅ |
| 5 | Documents explicitly untouched (byte-for-byte), tested | `tests/` | ✅ |
| 6 | Mobile `<Avatar>` requests the thumbnail for avatars ≤ 48 px; console row avatars likewise | `mobile/`, `admin-dashboard/` | ✅ |
| 7 | Config: `PROFILE_PHOTO_MAX_DIMENSION`, `_THUMB_DIMENSION`, `_WEBP_QUALITY`, `MAX_PHOTO_PIXELS`; `Pillow==13.0.0` pinned | `config.py`, `requirements.txt` | ✅ |
| 8 | 14 tests → **401 passed**, 94 % | `tests/test_profile_photo_processing.py` | ✅ |
| 9 | Docs: new doc 20, contract §3.4, README, this roadmap | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Suite | `python -m pytest` | **401 passed** (106 s) |
| PostgreSQL parity | `TEST_DATABASE_URL=… pytest` | **401 passed** (173 s) |
| Contract | `python -m scripts.check_contracts` | 98 / 98, exit 0 |
| Live upload (12 MP, GPS, orientation 6) | nginx + TLS + production env | 0.79 MB → **14,834 B** 512×512 WebP, EXIF none |
| Thumbnail variant | same | **176 B** 128×128, own ETag |
| Document untouched | `/uploads/verification` | 263,643 B in → 263,643 B stored |
| Bomb refused | crafted 69-byte PNG, 30000×30000 | `422 PHOTO_TOO_LARGE` |
| Console | Playwright | 13 rows · 3 avatars · **6/6** requests used `size=thumb` · 0 errors |
| Mobile | `tsc --noEmit` · `expo export -p android` | clean · 4,204,847 B |

---

## 5.13 Phase 15 — photo moderation (post-roadmap extension)

Closes the gap both previous phases ended on: a member could not report a specific
picture. Detail: [`21-photo-moderation.md`](21-photo-moderation.md).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | `ReportCategory.PROFILE_PHOTO`, `PhotoReportReason` (4 reasons), `reports.photo_reason` + `reports.reported_photo_asset_id` | enum, model, migration `b4f0a91c73de` | ✅ |
| 2 | `POST /users/{id}/photo/report` — 5/min, one open photo report per member, refuses self/no-photo/duplicates | `report_service.create_photo_report` | ✅ |
| 3 | **Evidence pinning**: the reported file survives a photo replacement, an admin removal and the orphan sweep | `media_service.set_profile_photo` / `clear_profile_photo` / `_reference_sets` | ✅ |
| 4 | `PATCH /admin/reports/{id}` gains `remove_photo` (photo reports only) → clears the picture, notifies the member, audits `REMOVE_PROFILE_PHOTO` | `admin_service.update_report` | ✅ |
| 5 | Admin queue shows the reason, the pinned evidence and the removal switch | console *Reports & complaints* | ✅ |
| 6 | Mobile: flag button on the driver card → `app/report-photo/[userId].tsx` | `mobile/` | ✅ |
| 7 | Notification templates `PHOTO_REMOVED`, `ADMIN_NEW_PHOTO_REPORT` | `notification_service` | ✅ |
| 8 | 20 tests → **421 passed**, 94 % | `tests/test_photo_moderation.py` | ✅ |
| 9 | Docs: new doc 21, contract §3.4/§3.9, README, runbook, this roadmap | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| Suite | `python -m pytest` | **421 passed** (114 s) |
| PostgreSQL parity | `TEST_DATABASE_URL=… pytest` | **421 passed** (184 s) |
| Migrations | `alembic upgrade head` · `alembic check` | applied on SQLite + PostgreSQL; no new operations |
| Contract | `python -m scripts.check_contracts` | 99 / 99, exit 0 |
| Live report through nginx | `POST /users/{id}/photo/report` | 201 · `PROFILE_PHOTO` · `OPEN` |
| Resolve + remove (service) | `PATCH /admin/reports/{id}` | photo cleared · evidence 200 · member 404 · notification sent |
| Console | Playwright | photo row + reason chip + evidence decoded + removal switch · 0 errors |
| Mobile | `tsc --noEmit` · `expo export -p android` | clean · 4,212,670 B |

---

## 5.14 Phase 16 — operations handbook (post-roadmap extension)

Every previous phase ends in a document written for whoever inherits the work. This one
is different: it is written for the **ride-share office**, printed, signed and filed.
Detail: [`22-operations-handbook.md`](22-operations-handbook.md) ·
[`22-operations-handbook.pdf`](22-operations-handbook.pdf).

| # | Deliverable | Where | Status |
| --- | --- | --- | --- |
| 1 | Ten-page handbook: what runs where, day-one checklist, daily/weekly/monthly routine, health panel, eight incident playbooks, backup + restore proof, release procedure, limits table, escalation table | `documentation/22-operations-handbook.md` | ✅ |
| 2 | Print-ready PDF generated from that Markdown through a self-contained HTML page (no external CSS or fonts), A4, footer page numbers | `scripts/build_handbook_pdf.py` | ✅ |
| 3 | Sign-off page: handover acceptance, day-one completion, first restore rehearsal | handbook §Sign-off | ✅ |
| 4 | Cross-linked from README, the docs index and the runbook; every number matches docs 17–21 | `documentation/` | ✅ |

**Verification log**

| Check | Command | Result |
| --- | --- | --- |
| PDF build | `python scripts/build_handbook_pdf.py` | **10 pages · 139 KB**, footers on every page |
| Content check | `pypdf` text extraction of page 1 and page 10 | title, front matter and sign-off render correctly |
| Visual check | Chromium screenshot of the rendered HTML | tables, code blocks and headings print cleanly (see §2 of the handbook) |
| Consistency | limits table vs `config.py` / nginx conf | 5 MB documents, 2 MB photos, 40 MP, 60 r/s edge, 30 min / 30 day sessions |
| Suite (unchanged) | `python -m pytest` | **421 passed** |
