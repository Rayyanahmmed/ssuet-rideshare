# SSUET RideShare 🚗🏍️

**University car & bike pooling platform for Sir Syed University of Engineering & Technology (SSUET), Karachi.**

Students and teachers publish the journeys they already make between home and
campus; other verified members of the SSUET community discover those journeys and
request to travel together — free, or sharing fuel cost offline.

> This is a **ride-matching / pooling** product (Careem-quality UX, own identity),
> not a taxi-hailing app: no fares, no dispatch, no in-app payments.

---

## Status

| Phase | Scope | State |
|---|---|---|
| **1** | Architecture, database design, backend foundation, scaffolds | ✅ **complete & runnable** |
| **2** | Authentication, sessions, roles, university verification | ✅ **complete & runnable** |
| **3** | Core ride system: vehicles, publish, explore, request, accept + maps | ✅ **complete & runnable** |
| **4** | Trip lifecycle: start, complete (both sides), cancel, no-show + housekeeping | ✅ **complete & runnable** |
| **5** | Real-time trip chat (WebSocket + REST fallback) & notifications with Expo push | ✅ **complete & runnable** |
| **6** | Admin dashboard: users, verification, vehicles, rides, trips, reports, analytics, settings | ✅ **complete & runnable** |
| **7** | Reviews & ratings, reports & complaints, blocking, privacy/IDOR hardening | ✅ **complete & runnable** |
| **8** | Journey tests, coverage, load sanity, Android release config, testing & admin docs | ✅ **complete** |
| **9** | Verification document upload: media storage, authorised streaming, in-app photo picker, admin viewer | ✅ **complete & runnable** |
| **10** | Vehicle photo & registration uploads, admin Proof column, orphan sweep + storage overview | ✅ **complete & runnable** |
| **11** | Production deployment: systemd + gunicorn, nginx TLS/console/API, backups, smoke test, PostgreSQL parity, CI | ✅ **complete & rehearsed** |
| **12** | Observability & load validation: request correlation, `/admin/health` panel, monitoring timer + alerts, capacity measured on PostgreSQL | ✅ **complete** |
| **13** | Profile photos: real uploads (no more pasted links), member-visible avatars in the app and the console | ✅ **complete** |
| **14** | Image normalisation: EXIF/GPS stripped, orientation applied, 512 px WebP + cached 128 px thumbnails, decompression-bomb guard | ✅ **complete** |
| **15** | Photo moderation: members report a picture, the file is pinned as evidence, the office resolves and can remove it | ✅ **complete** |
| **16** | Operations handbook: a printable handover for the ride-share office (day one, routine, playbooks, backups, sign-off) | ✅ **complete** |

Full checklist: [`documentation/05-roadmap-and-progress.md`](documentation/05-roadmap-and-progress.md)

---

## Repository layout

```
SSUET-RideShare/
├── backend/                    FastAPI + SQLAlchemy + Alembic (Python)
│   ├── app/
│   │   ├── api/v1/             versioned routers: auth, users, vehicles, rides, requests, trips, chat, notifications, admin
│   │   ├── core/               settings, security, logging, error envelope
│   │   ├── db/                 declarative base, session, column types
│   │   ├── models/             18 tables — the real database design
│   │   ├── schemas/            Pydantic contracts (grows per phase)
│   │   └── services/           business logic (admin bootstrap in Phase 1)
│   ├── alembic/                migrations (single owner of the schema)
│   ├── scripts/seed.py         realistic development data
│   └── tests/                  pytest suite (314 tests, 94% coverage)
├── mobile/                     Expo + React Native + TypeScript (Phases 1–5 complete)
├── admin-dashboard/            React + Vite + Tailwind admin console (Phase 6 complete)
├── database/schema.prisma      reference / documentation schema
├── documentation/              architecture, DB, API, journeys, roadmap, risks
├── docker-compose.yml          PostgreSQL + API
└── .env.example
```

---

## Run it on your own machine

**Unzipped the project and want the shortest path to a running system? Read
[`START-HERE.md`](START-HERE.md)** — three terminals, fifteen commands, expected output after
each step, and a troubleshooting table.

Still want the reasoning? **[`documentation/23-run-it-yourself.md`](documentation/23-run-it-yourself.md)**
is the step-by-step guide: backend on SQLite (no database server), the admin console, the
app on a real phone through **Expo Go**, and building the **APK** (EAS cloud build or local
Gradle) — including the LAN-IP mistake that wastes everyone's first hour.

## Quick start — backend (zero external services, SQLite)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # then edit at least JWT_SECRET_KEY / ADMIN_PASSWORD
# .env.example already points at SQLite (a file, no server). PostgreSQL is one uncommented
# line away — see "Quick start — with PostgreSQL" below.

python -m scripts.seed        # optional but recommended: realistic demo data
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

* API docs → <http://localhost:8000/docs>
* Liveness → `GET /api/v1/health` · DB readiness → `GET /api/v1/health/ready`
* Client bootstrap (university coords, feature flags) → `GET /api/v1/meta`

### Try the authentication flow

```bash
# sign in as a seeded student
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ali@ssuet.edu.pk","password":"Password123!"}'

# use the access token
curl -s localhost:8000/api/v1/auth/me -H "Authorization: Bearer <access_token>"
```

### Quick start — with PostgreSQL (recommended, matches production)

```bash
cp .env.example .env                          # root (docker-compose values)
docker compose up -d db
cd backend && cp .env.example .env            # DATABASE_URL already points at localhost:5432
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or run everything in containers: `docker compose up --build`
(the API container runs `alembic upgrade head` before starting uvicorn).

---

## Seeded development accounts

`python -m scripts.seed --reset` creates 10 users, 6 vehicles, 8 open rides, 1
matched trip with chat, 1 completed trip with reviews, and 1 open complaint.

| Email | Role | Note |
|---|---|---|
| `ali@ssuet.edu.pk` | Student (verified) | drives a Corolla, 3 published rides |
| `fatima@ssuet.edu.pk` | Student (verified) | has a matched trip with chat + a pending request |
| `ahmed@ssuet.edu.pk` | Student (verified) | completed 1 trip, rated 5.0 |
| `drfaheem@ssuet.edu.pk` | Teacher (verified) | free rides, morning |
| `usman@ssuet.edu.pk` | Student (suspended) | complaint demo in the admin panel |

**Password for every seeded account:** `Password123!` (dev only — never reused in production).

---

## Administrator account (§17)

The admin is created from environment variables on backend start-up, **once**:

```env
ADMIN_NAME=System Administrator
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeThisToSomethingStrong!
ADMIN_BOOTSTRAP_ENABLED=true
```

* password is Argon2-hashed before insert — plaintext never reaches PostgreSQL;
* if the account already exists the bootstrap **does nothing** — a restart never
  resets the password;
* set `ADMIN_BOOTSTRAP_ENABLED=false` after the first successful start;
* in production the app refuses to boot with a placeholder/short `JWT_SECRET_KEY`
  or with `ADMIN_BOOTSTRAP_ENABLED=true` and an empty `ADMIN_PASSWORD`.

---

## Housekeeping jobs

Stale rides expire and abandoned trips close themselves every
`MAINTENANCE_INTERVAL_MINUTES` (default 15). Run them manually or from cron with:

```bash
cd backend
python -m scripts.expire_stale_rides --grace 60     # expire unclaimed rides
python -m scripts.expire_stale_rides --dry-run      # report only
```

## Tests

```bash
cd backend
python -m pytest              # 314 tests (incl. 10 end-to-end journeys)
python -m pytest --cov=app    # 94% statement coverage
python -m pytest -v tests/test_auth.py
```

`tests/test_journeys.py` (10 stories) walks complete user journeys through the
real HTTP surface — publish → discover → request → accept → chat → start → complete →
rate, plus seat reuse, no-show, verification gating, housekeeping and the
report → suspension → resolution path — so a break *between* phases fails the build.
`tests/test_reviews.py` (25 tests) proves reviews are limited to completed trips and
their participants, one per side, that a comment must say something and that the
subject's average is **recomputed** (so a hidden review really leaves the average).
`tests/test_reports.py` (20 tests) proves a report can only be aimed at somebody the
reporter actually shared a trip or ride with, that the office's resolution reaches the
reporter, and that blocking removes a member from Explore and from chat.
`tests/test_security.py` (19 tests) is the privacy/IDOR net: it walks Explore, ride
detail and public-profile payloads for leaked phone numbers, exact coordinates or home
addresses, and attacks every id-taking endpoint as a stranger.
`tests/test_admin.py` (38 tests) proves the console is guarded — members get `403`,
anonymous callers `401`, admins cannot be suspended, suspending a driver cancels
their open rides, force-cancelling a ride cascades to its trips, every mutation
appends an audit row, and `/admin/settings` never serialises a secret.
`tests/test_auth.py` covers signup validation, duplicate detection, login
enumeration-resistance, suspended accounts, refresh-**rotation with reuse
detection**, logout, forgot/reset (single-use tokens), email confirmation, manual
verification, profile escalation attempts, blocking and rate limiting.
`tests/test_db_constraints.py` proves the business rules at the **database** level, e.g.
`test_second_live_trip_on_same_ride_is_impossible` (one confirmed passenger),
`test_only_one_pending_request_per_passenger_and_ride`,
`test_review_is_unique_per_trip_and_author`, foreign keys, rating ranges.

---

## Migrations

```bash
cd backend
alembic upgrade head                                  # apply
alembic revision --autogenerate -m "describe change"  # after editing models
alembic downgrade -1                                  # roll back one step
```

Alembic is the **only** migration tool that touches a real database.
`database/schema.prisma` is a reviewed reference artifact (Prisma Client is not
part of the Python runtime).

---

## Mobile app (Expo)

```bash
cd mobile
npm install
cp .env.example .env          # set EXPO_PUBLIC_API_URL to your LAN IP, e.g. http://192.168.1.5:8000/api/v1
npx expo start
eas build -p android --profile preview   # installable APK for FYP testing
```

> Use your machine's **LAN IP**, not `localhost`, when testing on a physical
> Android device.

**What works today (Phases 1–7):** onboarding → login/signup → verification →
Home (next trip + real journeys + unread badge) → **Explore with filters** →
**Publish a 5-step ride** → **Ride details + request to join** → **My Rides
(published / requested / accept / reject)** → **Trip screen (start, both-sides
completion, cancel, no-show, call)** → **Live trip chat (typing, presence, read
receipts, REST fallback)** → **Notifications** → **Rate your trip (1–5 + comment)** → **Report a problem** →
**My ratings / My reports / Blocked members** → Vehicles → Profile.

* Maps: the map runs on OpenStreetMap by default and needs no key. A commercial map
  key (e.g. Geoapify) is pasted in **Admin → Map API**; no code change or rebuild.
  If the key fails or runs out, the map falls back to OpenStreetMap automatically.
* `react-dom` is pinned to `19.1.0` to match `react`; a transitive
  `react-dom@19.3.1` otherwise breaks `npm install` with `ERESOLVE` on Expo SDK 54.
* `babel-preset-expo` is a devDependency — `expo export` / `eas build` need it.
* Bundle sanity check: `npx expo export --platform android` (currently ~4.1 MB HBC,
  zero bundling errors).

## Admin dashboard (React + Vite)

```bash
cd admin-dashboard
npm install
cp .env.example .env          # VITE_API_BASE_URL=/api/v1 (proxied) or an absolute API URL
npm run dev                   # http://localhost:5173  → sign in with the admin account
```

**What works today (Phase 6)** — every module reads the real `/api/v1/admin/*` API:

* **Dashboard** — member/verification/vehicle/suspension counters, published/active/
  completed trips, open reports, 14-day signup-vs-rides area chart, trip-status
  doughnut, recent admin activity.
* **Users** — search by name/email/university ID, filters for role, account state and
  verification, dossier drawer (vehicles, recent rides, submissions, trip & report
  counters, approximate home area) and the four decisions: verify, reject, suspend,
  reactivate — each with a reason and an audit entry.
* **Verification requests** — pending queue with approve/reject.
* **Vehicle verification** — queue + search, approve or reject with a note the owner sees.
* **Published rides** — filter by status, direction, area and date; force-cancel with a
  reason (cancels the trip and notifies both members).
* **Active / Completed trips** — participants, timings, status.
* **Reports & complaints** — handling dialog with under-review / resolve / dismiss and a
  mandatory resolution note.
* **Suspended accounts** — reactivate in one click.
* **Analytics** — growth series, completion/cancellation rate, average rating, fuel and
  vehicle mix, travel direction, busiest pickup areas/destinations, and the full
  administrative action log.
* **Reports & Complaints** — two tabs: the complaint queue with resolve/dismiss notes,
  and **review moderation** (search, visibility and rating filters, hide/restore with a
  reason; hiding recomputes the subject's average).
* **Settings** — effective configuration as **read-only flags** (never secrets), plus
  service health. Nothing that changes behaviour is editable from the browser.

---

## Release (v1.0.0)

```bash
# backend
cd backend && python -m pytest                # 314 passing, 94% coverage
alembic upgrade head                          # PostgreSQL production schema

# admin console
cd ../admin-dashboard && npm ci && npm run build

# mobile — installable APK for the FYP demo
cd ../mobile && npx tsc --noEmit
eas build -p android --profile preview        # APK
eas build -p android --profile production     # AAB for the Play Console
```

Release notes, the physical-device checklist and the known limitations live in
[`documentation/12-phase8-testing-and-release.md`](documentation/12-phase8-testing-and-release.md).
Ops day-to-day: [`documentation/13-admin-runbook.md`](documentation/13-admin-runbook.md).
What was audited for the release candidate (contracts, clean-room boot, secrets, copy):
[`documentation/14-release-candidate-audit.md`](documentation/14-release-candidate-audit.md).

```bash
cd backend && python -m scripts.check_contracts    # every shipped route is documented, and vice versa
```

### Verified numbers

| Metric | Value |
| --- | --- |
| Backend tests | **422 passing on SQLite and on PostgreSQL 17** (202 system/feature + 38 admin + 25 reviews + 20 reports + 19 security + 39 media/uploads + 22 profile photos + 14 image processing + 20 photo moderation + 12 observability + 10 journeys + 1 push auth) |
| Backend coverage | **94%** of 4,854 statements (`documentation/testing/coverage.txt`) |
| API surface | **99 routes**, all documented (audited by `scripts/check_contracts.py`) |
| Explore under load | Phase 8 (SQLite, 1 worker): 102 rps / p50 179 ms · Phase 12 (PostgreSQL, 5 workers, nginx): **145 rps / p50 ~100 ms**, 0 errors in 1,400 requests (`documentation/testing/load-postgres.txt`) |
| Single-request latency | **11.6–13 ms** for an Explore page (20 rides, 18.2 KB), of which 2.5 ms is SQL |
| Mobile bundle | **4.20 MB** HBC (4,204,847 B), `tsc` clean |
| Profile photos | Uploaded ≤ 2 MB · stored as **512 px WebP with no EXIF/GPS** (a 12 MP 0.79 MB photo → **14.8 KB**, 53× smaller) · 128 px thumbnail variant · readable by members, **401** anonymous · reportable, evidence pinned |
| Admin console | `tsc` clean, `npm run build` ✓, 11 modules + review moderation, 0 console errors over 12 page loads |
| Production stack | nginx TLS + gunicorn rehearsed: `deploy/smoke.sh` **17/17**, wss chat, 413 at the edge, 429 rate limit |
| Monitoring | `deploy/monitor.sh` verified healthy **and** failing (exit 2 + webhook) · `/admin/health` live |
| Handover pack | 10-page printable PDF built from the repo Markdown (`scripts/build_handbook_pdf.py`), with sign-off page |
| Clean-room boot | migrate → seed → 14/14 HTTP checks on a brand-new database |

## Documentation

| Doc | Contents |
|---|---|
| [01-architecture](documentation/01-architecture.md) | components, layers, request lifecycle, mobile/admin structure, decisions |
| [02-database-design](documentation/02-database-design.md) | ER diagram, table catalogue, status machines, transactions, indexes |
| [03-api-contracts](documentation/03-api-contracts.md) | every endpoint, filters, error codes, rate limits |
| [04-user-journeys](documentation/04-user-journeys.md) | personas, the 6 key journeys, screen map, home-screen composition |
| [05-roadmap-and-progress](documentation/05-roadmap-and-progress.md) | phase deliverables, live progress board, definition of done |
| [07-phase3-ride-system](documentation/07-phase3-ride-system.md) | Phase 3 backend endpoints, mobile screens, concurrency & privacy decisions |
| [08-phase4-trip-lifecycle](documentation/08-phase4-trip-lifecycle.md) | Phase 4 state machine, trip endpoints, maintenance jobs, mobile trip screens |
| [09-phase5-chat-notifications](documentation/09-phase5-chat-notifications.md) | Phase 5 socket protocol, chat screens, notification/push delivery contract, FCM setup |
| [10-phase6-admin-dashboard](documentation/10-phase6-admin-dashboard.md) | Phase 6 admin endpoints, authorisation, console modules, audit trail, live verification |
| [11-phase7-trust-quality](documentation/11-phase7-trust-quality.md) | Phase 7 reviews, reports & blocking, privacy/IDOR hardening, mobile trust screens |
| [12-phase8-testing-and-release](documentation/12-phase8-testing-and-release.md) | Phase 8 test strategy, coverage, load sanity, EAS/APK release steps, device checklist |
| [13-admin-runbook](documentation/13-admin-runbook.md) | day-to-day operations: queues, incidents, metrics, health, configuration, handover |
| [14-release-candidate-audit](documentation/14-release-candidate-audit.md) | contract audit, clean-room boot, secrets/hygiene, stale-copy sweep, console sweep, verdict |
| [15-phase9-media-pipeline](documentation/15-phase9-media-pipeline.md) | Phase 9 verification uploads: storage model, security rules, live evidence, configuration |
| [16-phase10-vehicle-documents](documentation/16-phase10-vehicle-documents.md) | Phase 10 vehicle photo/registration uploads, admin Proof column, orphan sweep, storage overview |
| [17-production-deployment](documentation/17-production-deployment.md) | Phase 11 deployment: systemd/nginx/backups/smoke test, PostgreSQL parity, CI pipeline, handover checklist |
| [18-observability-and-load](documentation/18-observability-and-load.md) | Phase 12 request correlation, health panel, monitoring + alerts, measured capacity |
| [19-profile-photos](documentation/19-profile-photos.md) | Phase 13 profile photos: the semi-public visibility rule, uploads, avatars everywhere |
| [20-image-normalisation](documentation/20-image-normalisation.md) | Phase 14 EXIF stripping, orientation, 512 px WebP, thumbnails, bomb guard |
| [21-photo-moderation](documentation/21-photo-moderation.md) | Phase 15 reporting a picture, pinned evidence, resolve-and-remove |
| [06-risks-and-external-setup](documentation/06-risks-and-external-setup.md) | external APIs, key restriction, 14 risks & mitigations |

---

## Security posture (implemented so far)

* Argon2id password hashing; no plaintext password is ever stored or logged.
* Short-lived access JWT + opaque refresh token stored **SHA-256 hashed**, rotated
  on every use with reuse detection (a replayed token kills the whole session family).
* Rate limiting on auth endpoints (login 10/min, register 5/min, reset 5/min).
* Login and password-reset responses never reveal whether an email is registered.
* Mobile tokens live in the platform keystore (`expo-secure-store`); admin tokens in
  `sessionStorage` and are revoked on sign-out.
* Fail-fast production config validation; secret-redaction log filter.
* Ownership/permission checks are always re-derived server-side (§26.9).
* One-confirmed-passenger invariant enforced by a **partial unique index**.
* Reviews are tied to completed trips and to the two participants; one per side,
  enforced by a unique constraint, with recomputed (never incremented) averages.
* Reports validate that the subject really shared the journey; the resolution note
  reaches the reporter.
* A privacy sweep test fails the build if Explore, ride detail or a public profile ever
  exposes a phone number, email, home address or exact meeting coordinates.
* `.env` files git-ignored; every component ships a `.env.example`.

## License

Academic project (FYP) — Sir Syed University of Engineering & Technology, Karachi.
