# 14 · Release-candidate audit (v1.0.0)

**Purpose.** The eight delivery phases each proved their own slice. This pass audits the *whole
repository as a stranger would receive it*: does the documentation match the shipped API, does a
fresh machine boot from zero, is any secret committed, is any user-facing copy describing software
that does not exist. Nothing here adds features — every finding is either fixed or recorded.

Date: 6 November 2026 · Scope: `backend/`, `mobile/`, `admin-dashboard/`, `documentation/` · Result:
**release candidate accepted**, 4 defects found and fixed, 0 open.

---

## 1. Contract audit — code vs. documentation

`backend/scripts/check_contracts.py` diffs the live FastAPI route table (`app.openapi()`) against
the paths named in `documentation/*.md`.

```bash
cd backend && python -m scripts.check_contracts        # add --json for machine output
```

| Run | Implemented | Documented | Verdict |
| --- | --- | --- | --- |
| First run | 89 | 99 | 2 shipped routes undocumented, 10 documented routes that do not exist |
| After fixes | 89 | 87 | ✓ every shipped route is documented and every documented route exists (exit 0) |
| After Phase 9 (media) | 92 | 92 | ✓ unchanged discipline — new routes shipped documented, see doc 15 |

Drift found and corrected:

1. **Device tokens** — doc 03 listed `/notifications/device`; the API ships
   `POST /notifications/devices` and `DELETE /notifications/devices/{token}`.
2. **Reviews & reports** — doc 03 §3.10 described a `/trips/{id}/reviews` shape from the design
   draft. The shipped contract is `/reviews/trips/{id}`, `/reviews/pending`, `/reviews/me/received`,
   `/reviews/users/{id}`, `/reports`, `/reports/{id}` plus the two block routes.
3. **Trip lifecycle** — `start`/`complete` moved to `/trips/{id}/start` and `/trips/{id}/complete`
   in Phase 4; doc 03 still showed them under `/rides/{id}`.
4. Two routes were genuinely undocumented: `POST /auth/logout-all` and
   `POST /auth/resend-verification`. Both now appear in doc 03.

The checker is deliberately conservative so it stays useful: it normalises `{param}` → `{}`, strips
query strings, ignores the app-level docs paths (`/docs`, `/redoc`, `/openapi.json`), ignores
Markdown table cells that are HTTP verbs, and matches on path (a shared `GET/POST | /vehicles` row
documents both). It exits 1 only for a shipped route nobody documented — a doc describing a route
we removed is reported as informational, because design drafts intentionally describe intended
shape.

**Run it before every release** — see the ritual in doc 12 §5.

---

## 2. Clean-room boot — does a new machine work from zero?

No existing database was reused. A brand-new SQLite file was created purely by the migration
chain, seeded by the shipped script, and then exercised over HTTP:

```bash
cd backend
export DATABASE_URL="sqlite+pysqlite:///./cleanroom.db" AUTO_CREATE_TABLES=false
alembic upgrade head           # 75965bfe895c → 550e18b493a6
python -m scripts.seed         # 6 vehicles · 8 open rides · 1 matched trip · 1 completed trip
uvicorn app.main:app --port 8011
```

| # | Check | Result |
| --- | --- | --- |
| 1 | `GET /health` | 200, `status=ok` |
| 2 | `GET /health/ready` (DB + migrations) | 200, database ok |
| 3 | `GET /meta` bootstrap payload | 200, `max_confirmed_passengers=1` |
| 4 | Student login with the documented seed password | 200, role `STUDENT` |
| 5 | Explore feed shows seeded rides | 7 rides |
| 6 | `GET /trips/mine` | 200 |
| 7 | `GET /notifications` | 200, 1 unread |
| 8 | `GET /reviews/pending` | 200 |
| 9 | `GET /reports` | 200 |
| 10 | Admin login with the documented bootstrap credentials | 200, role `ADMIN` |
| 11 | `GET /admin/dashboard` | 200 — 11 users, 9 published rides, 1 open report |
| 12 | `GET /admin/users` | 200, 11 members |
| 13 | `GET /admin/reviews` | 200, 2 reviews |
| 14 | `GET /admin/reports` | 200, 1 report |

**14/14.** The documented first-run path (migrate → seed → login as the printed credentials) is
accurate, and `AUTO_CREATE_TABLES=false` proves the Alembic chain alone produces a working schema.
The throwaway database was deleted afterwards; the audit is reproducible in about four minutes.

Container path: `docker-compose.yml` was reviewed by hand rather than executed (no Docker daemon in
this environment). It is internally consistent — Postgres with a `pg_isready` healthcheck, the API
gated on `condition: service_healthy`, `alembic upgrade head && uvicorn` as the command, and a
`HEALTHCHECK` in the image that polls `/api/v1/health`. Every `${VAR}` it references has a default
and is listed in the root `.env.example`.

---

## 3. Secrets and hygiene

| Check | Finding |
| --- | --- |
| Provider keys (`sk-…`, `AIza…`, `AKIA…`, PEM blocks) anywhere in source/docs | **none** |
| `.env` committed | no — `backend/.env` exists locally only; `.gitignore` has `.env`, `.env.*`, `!.env.example` |
| Databases committed (`*.db`, `*.sqlite3`) | excluded by `.gitignore` |
| Admin credentials in code | bootstrap reads `ADMIN_EMAIL` / `ADMIN_PASSWORD`; the demo pair is only in the seed script and docs |
| Docker build context | **fixed** — `backend/.dockerignore` added; previously `COPY . .` would have pulled `.venv/`, `*.db`, `.env` and `tests/` into the image |

The two documented demo secrets (`Password123!`, `Admin@SSUET2026`) are seed data for a local
SQLite file, and doc 12 §7 plus doc 13 §1 tell the operator to replace them before any real
deployment. They are deliberately not read from the environment in `seed.py` so the documented
login keeps working on a fresh clone.

---

## 4. Stale copy removed from the mobile app

Four strings still promised work that shipped differently or never happened. All are now accurate:

| File | Was | Now |
| --- | --- | --- |
| `app/(tabs)/profile.tsx` | footer `SSUET RideShare · Phase 7 · v0.7.0` | `SSUET RideShare · v1.0.0` |
| `app/(tabs)/my-rides.tsx` | "Ratings will be added in Phase 7" | "After that you can rate each other." (reviews shipped) |
| `app/verification.tsx` (header) | "Document upload arrives with the media pipeline in Phase 7" | states plainly that there is no in-app upload; a photo link is pasted and an admin opens it |
| `app/verification.tsx` (field hint) | same promise | "Upload the photo to your Drive, then paste a shareable https link here." |
| `src/lib/schemas.ts` | "until map/places autocomplete lands (Phase 3)" | explains the area list is the no-Maps-key fallback (§13) |

`grep -rn "Phase [0-9]" mobile/app mobile/src` now returns nothing, and `tsc --noEmit` is clean.

---

## 5. Admin console sweep (browser)

Logged in as `admin@example.com` and visited every sidebar destination plus an unknown URL — 12
page loads, console watched for errors and failed requests:

| Route | Page | Rows |
| --- | --- | --- |
| `/` | Operations overview | 0 (cards + recent activity) |
| `/users` | Users | 11 |
| `/verifications` | Verification requests | 1 |
| `/vehicles` | Vehicle verification | 1 |
| `/rides` | Published rides | 11 |
| `/trips/active` | Active trips | 2 |
| `/trips/completed` | Completed trips | 2 |
| `/reports` | Reports & complaints | 1 |
| `/suspended` | Suspended accounts | 1 |
| `/analytics` | Analytics | 5 |
| `/settings` | Settings | 0 (form) |
| `/does-not-exist` | Page not found | — |

**0 console errors, 0 responses ≥ 400, no placeholder screens left.** The 404 page renders the
shared shell with a link home (`documentation/screenshots/shot-404.png`).

---

## 6. Verdict and what is still honestly missing

Release candidate **accepted**: documentation matches the shipped API, a clean machine boots,
no secrets are committed, no user-facing promise is unfulfilled.

Known gaps — unchanged, documented, and by design rather than oversight:

- No payment gateway: fuel share is settled in cash between members.
- ~~No in-app file upload: verification uses a pasted link.~~ **Fixed in Phase 9** — see
  [`15-phase9-media-pipeline.md`](15-phase9-media-pipeline.md). A pasted link is still
  accepted as a fallback, but the app now uploads the photo and the file is readable only
  by its owner and the reviewing administrator.
- No Google Maps key by default: the map screen degrades to a picker of Karachi areas.
- No SMTP by default: mail logs to the console (`EMAIL_DELIVERY=log`).
- Push notifications need an Expo project id; in-app notifications work without it.
- One confirmed passenger per ride; extra requests stay pending.
- No APK is built in this environment (no Android SDK); `eas build` instructions and a verified
  `expo export` bundle are the local proof — doc 12 §4.

Next infrastructure work, in order of value: multipart media upload (removes the pasted-link
workaround), Postgres in CI (the suite runs on SQLite), and a rate-limit/abuse pass on the auth
endpoints.
