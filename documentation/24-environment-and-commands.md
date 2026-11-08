# 24 · Environment variables, commands, and what "integrating the API" means

Short answer to the question that prompted this document:

> **There is no third-party API to integrate.** The mobile app and the admin console already
> talk to *your own* backend — the 99-route API in this repository. "Integration" is one line:
> `EXPO_PUBLIC_API_URL` must point at the machine running `backend/`. The system is fully
> functional without a map API key, without SMTP and without Expo push; those three are
> **optional services that upgrade the experience**, and each one degrades instead of breaking
> (matrix in §2).

Everything below was executed in the development sandbox. Test count after this phase's
change: **422 passed**.

---

## 1. How the pieces fit (nothing here is external)

```
┌──────────────┐   HTTPS/JSON   ┌──────────────────┐   SQL    ┌──────────────┐
│  Mobile app  │ ─────────────► │  Backend API     │ ───────► │  SQLite /    │
│  (Expo/RN)   │ ◄───────────── │  FastAPI :8000   │ ◄─────── │  PostgreSQL  │
└──────────────┘   JWT bearer   └──────────────────┘          └──────────────┘
       ▲                              ▲      │
       │  same API, browser           │      └── media files on disk (MEDIA_ROOT)
┌──────────────┐                      │
│ Admin console│ ─────────────────────┘
│ (React :5173)│
└──────────────┘
```

| Optional external service | If you skip it | Where it is configured |
| --- | --- | --- |
| **Map tiles** | Nothing — the app draws a WebView map from OpenStreetMap tiles proxied by the backend. Swap in Geoapify/MapTiler whenever you like. | Backend `MAP_PROVIDER` (seed) · console → **Map API** (live, rotatable) |
| **SMTP** | Verification / reset emails are **printed to the backend console** (`DEV EMAIL …`). Copy the link from there. | `SMTP_HOST` … in `backend/.env` |
| **Expo push** | Notifications are stored and shown in the app's **bell list**; no system pop-up. | `EXPO_PUSH_ENABLED`, `EXPO_ACCESS_TOKEN`, `EAS_PROJECT_ID` |

---

## 2. Is it functional without any keys? — the matrix

| Feature | Zero keys | Needs |
| --- | --- | --- |
| Register / login / JWT refresh | ✅ | — |
| Student/employee ID verification + admin approval | ✅ | — (documents upload locally) |
| Publish ride, search, request, accept/reject | ✅ | — |
| Trip lifecycle (start / complete / cancel), auto-expiry | ✅ | — |
| Chat + in-app notifications | ✅ | — (system banner needs Expo push) |
| Reviews, ratings, reports, blocking, photo moderation | ✅ | — |
| Profile photos (WebP, EXIF stripped, throttled) | ✅ | — |
| Admin console: every queue, users, rides, reports, health | ✅ | — |
| Email verification / password reset **by email** | ⚠️ console log only | SMTP |
| Map picker with pin, distance display | ✅ OSM tiles | Optional Geoapify key in Admin → Map API |
| Android **system** notification banner | ⚠️ in-app bell only | Expo project + EAS build |
| Anything else (payments, SMS, ID OCR) | — | not part of v1 by design (doc 22 §9) |

**So: yes — clone, fill one `.env` file, and the whole product works.** Add keys later without
touching code.

---

## 3. The three env files — exactly what to put

There is **no env file at the repository root** for local development (the root `.env.example`
is only for `docker-compose`). You need three files, one per component.

> Rule: `EXPO_PUBLIC_*` and `VITE_*` are **shipped to the phone/browser** — never put a secret
> in them. Secrets live only in `backend/.env`.

### 3a. `backend/.env` — the only file you must create

```bash
cd backend
cp .env.example .env
python -c "import secrets;print(secrets.token_urlsafe(48))"   # → paste into JWT_SECRET_KEY
```

Minimum working file (copy as-is, replace the two `CHANGE_ME` values):

```ini
# ---------- core ----------
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# ---------- database ----------
DATABASE_URL=sqlite+pysqlite:///./ssuet_dev.db
DB_ECHO=false

# ---------- security ----------
JWT_SECRET_KEY=<output of the secrets command above>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# ---------- admin account created on first boot ----------
ADMIN_NAME=System Administrator
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=Admin@SSUET2026
ADMIN_BOOTSTRAP_ENABLED=true

# ---------- university policy ----------
UNIVERSITY_EMAIL_DOMAINS=ssuet.edu.pk
AUTO_VERIFY_UNIVERSITY_EMAILS=true

# ---------- CORS (console + Expo web) ----------
CORS_ORIGINS=http://localhost:5173,http://localhost:8081
RATE_LIMIT_ENABLED=true

# ---------- housekeeping ----------
MAINTENANCE_INTERVAL_MINUTES=15
RIDE_AUTO_EXPIRE_GRACE_MINUTES=60

# ---------- media ----------
MEDIA_ROOT=./media
MAX_UPLOAD_BYTES=5242880

# ---------- optional: leave empty / false for local work ----------
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true
EMAIL_FROM=SSUET RideShare <no-reply@ssuet-rideshare.local>
APP_DEEP_LINK_BASE=ssuetrideshare://
ADMIN_WEB_URL=http://localhost:5173
MAP_PROVIDER=osm
GEOAPIFY_API_KEY=
SSUET_LATITUDE=24.9372
SSUET_LONGITUDE=67.1138
EXPO_PUSH_ENABLED=true
EXPO_ACCESS_TOKEN=
```

**Every backend variable, in full** (defaults are what you get if you delete the line):

| Variable | Required | What to put |
| --- | --- | --- |
| `ENVIRONMENT` | ✅ | `development` locally · `test` · `production` (production turns on strict checks) |
| `DEBUG` | — | `true` locally, `false` in production |
| `LOG_LEVEL` | — | `INFO` (or `DEBUG`; only these five are accepted) |
| `DATABASE_URL` | ✅ | `sqlite+pysqlite:///./ssuet_dev.db` **or** `postgresql+psycopg://user:pass@host:5432/db` — nothing else is accepted |
| `AUTO_CREATE_TABLES` | — | `true` (default) so SQLite needs no migrations; must be `false` for PostgreSQL |
| `DB_ECHO` | — | `false`; `true` prints every SQL statement |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | — | 5 / 10 local · 10 / 20 production |
| `JWT_SECRET_KEY` | ✅ | 48 random characters. **Empty** → an ephemeral secret is generated (all tokens die on restart). In `production`, a placeholder or <32 chars is a fatal startup error |
| `JWT_ALGORITHM` | — | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | — | `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | — | `30` |
| `ADMIN_BOOTSTRAP_ENABLED` | — | `true` creates the console admin once, on first boot only |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` | ✅ if bootstrap | the console login you will actually use |
| `SMTP_HOST` | optional | empty → emails printed to the console. Otherwise e.g. `smtp.ssuet.edu.pk` |
| `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_USE_TLS` | optional | `587` / mailbox / password / `true` |
| `EMAIL_FROM` | optional | `SSUET RideShare <rideshare@ssuet.edu.pk>` |
| `APP_DEEP_LINK_BASE` | optional | `ssuetrideshare://` — used inside email links |
| `ADMIN_WEB_URL` | optional | where console buttons in emails point (`http://localhost:5173`) |
| `UNIVERSITY_EMAIL_DOMAINS` | optional | `ssuet.edu.pk` (comma separated) |
| `AUTO_VERIFY_UNIVERSITY_EMAILS` | optional | `true` = university addresses skip manual approval and get student status |
| `MAP_PROVIDER` | optional | `osm` (default, no key) · `geoapify` · `maptiler`. Only seeds a fresh install — the live value comes from the console **Map API** tab |
| `GEOAPIFY_API_KEY` | optional | fallback key used only while no key is stored in the database. Prefer the console tab: it rotates without a restart |
| `SSUET_LATITUDE` / `SSUET_LONGITUDE` | optional | campus centre, `24.9372` / `67.1138` |
| `UNIVERSITY_AREA_LABEL` | optional | `SSUET, University Road, Karachi` (shown when maps are off) |
| `CORS_ORIGINS` | ✅ for the console | `http://localhost:5173`, plus your real domain in production |
| `RATE_LIMIT_ENABLED` | — | `true` (per-route limits: 5/min on reports and photo reports…) |
| `EXPO_PUSH_ENABLED` | — | `true`; set `false` if you have no Expo project and want quiet logs |
| `EXPO_ACCESS_TOKEN` | optional | only for Expo projects with *enhanced push security*; empty = send unauthenticated *(wired in this phase — previously the variable was documented but unused)* |
| `EXPO_PUSH_URL` | — | leave as-is unless you proxy push |
| `MAX_CONFIRMED_PASSENGERS` | — | `1` (v1 rule); up to 8 |
| `MIN_MINUTES_BETWEEN_DRIVER_RIDES` | — | `30` anti-spam gap between a driver's published rides |
| `DEFAULT_DISCOVERY_RADIUS_KM` | — | `25` |
| `PASSWORD_MIN_LENGTH` | — | `8` (8–64) |
| `EMAIL_VERIFICATION_TOKEN_MINUTES` | — | `1440` (24 h) |
| `PASSWORD_RESET_TOKEN_MINUTES` | — | `30` |
| `RIDE_AUTO_EXPIRE_GRACE_MINUTES` | — | `60` after departure, unclaimed rides become `EXPIRED` |
| `MAINTENANCE_INTERVAL_MINUTES` | — | `15` local · `0` in production (use cron instead) |
| `REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH` | — | `false` = a PENDING vehicle may publish; `true` = stricter |
| `MEDIA_ROOT` | ✅ | `./media` local · `/var/lib/ssuet-rideshare/media` production |
| `MAX_UPLOAD_BYTES` | — | `5242880` (5 MB) for verification documents |
| `MAX_PROFILE_PHOTO_BYTES` | — | `2097152` (2 MB) for avatars |
| `PROFILE_PHOTO_MAX_DIMENSION` / `_THUMB_DIMENSION` / `_WEBP_QUALITY` | — | `512` / `128` / `82` (normalisation, doc 20) |
| `MAX_PHOTO_PIXELS` | — | `40000000` decompression-bomb ceiling |
| `MEDIA_ORPHAN_RETENTION_DAYS` | — | `7` before unused uploads are swept |
| `SLOW_REQUEST_MS` | — | `500` — slower requests are logged and counted in `/admin/health` |

### 3b. `admin-dashboard/.env`

```bash
cd admin-dashboard
cp .env.example .env
```

```ini
# Leave empty in development: Vite proxies /api to the backend, so no CORS and no
# hardcoded host. Set it when the console is served from a different origin.
VITE_API_BASE_URL=
VITE_PROXY_TARGET=http://127.0.0.1:8000
```

| Variable | Required | What to put |
| --- | --- | --- |
| `VITE_API_BASE_URL` | — | empty locally · `https://rideshare.ssuet.edu.pk/api/v1` if the console is hosted separately |
| `VITE_PROXY_TARGET` | — | where `npm run dev` forwards `/api` (default `http://127.0.0.1:8000`) |

### 3c. `mobile/.env`

```bash
cd mobile
cp .env.example .env
```

```ini
# On a physical phone this MUST be your computer's LAN IP (find it: ipconfig / ifconfig).
# `localhost` means "the phone itself" and gives a network error.
EXPO_PUBLIC_API_URL=http://192.168.1.10:8000/api/v1

# Optional — filled in by `eas init` / `eas build:configure`; needed for push tokens.
EAS_PROJECT_ID=
```

| Variable | Required | What to put |
| --- | --- | --- |
| `EXPO_PUBLIC_API_URL` | ✅ | `http://<LAN-IP>:8000/api/v1` on a phone · `http://localhost:8000/api/v1` in an emulator · `https://rideshare.ssuet.edu.pk/api/v1` for a real build |
| *(no mobile map key)* | — | Map provider and key are set in Admin → Map API; rotating the key needs no rebuild |
| `EAS_PROJECT_ID` | optional | from `eas init`; without it no push tokens are registered |
| `EXPO_PUBLIC_*` anything else | — | would be public — never a password or secret |

`EXPO_PUBLIC_*` values are baked in at **build** time: after editing `.env`, restart
`expo start` (and rebuild an APK for the change to take effect).

---

## 4. Every command you need

### 4.1 Backend (Python 3.11+)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                      # then set JWT_SECRET_KEY + ADMIN_PASSWORD
python -m scripts.seed                    # demo data; --reset wipes domain tables first
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# with PostgreSQL instead of SQLite (uncomment the DATABASE_URL line first)
alembic upgrade head
alembic check                             # "No new upgrade operations detected"
```

Maintenance / operational scripts (all take the same env):

```bash
python -m scripts.expire_stale_rides         # what cron calls every 15 min in production
python -m scripts.sweep_media                # delete unreferenced uploads older than N days
python -m scripts.load_check --help          # measured-throughput load generator
python scripts/check_contracts.py            # verifies all routes are documented → 99/99
```

### 4.2 Tests

```bash
cd backend
python -m pytest -q                                   # 422 tests on SQLite
TEST_DATABASE_URL="postgresql+psycopg://ssuet:ssuet@localhost:5432/ssuet_test" python -m pytest -q
python -m pytest tests/test_photo_moderation.py -q     # one module
python -m pytest -q --cov=app --cov-report=term-missing # coverage (94 %)
```

### 4.3 Admin console (Node 20+)

```bash
cd admin-dashboard
npm install                 # add --legacy-peer-deps if you hit ERESOLVE
npm run dev                 # http://localhost:5173
npm run build               # production bundle → dist/
npx tsc --noEmit            # typecheck
```

### 4.4 Mobile app

```bash
cd mobile
npm install
npm run typecheck                      # tsc --noEmit
npx expo start --lan                   # QR → Expo Go on the phone
npx expo start --android               # or an attached emulator
npx expo export -p android             # proves the JS bundle builds (≈4.2 MB)

# APK — cloud (no Android SDK needed)
npx eas-cli@latest login
npx eas-cli@latest build -p android --profile preview      # → APK download link
npx eas-cli@latest build -p android --profile production   # → AAB for Play Store

# APK — local (JDK 17 + Android SDK)
npx expo prebuild -p android
cd android && ./gradlew assembleRelease        # Windows: gradlew.bat assembleRelease
```

### 4.5 Whole stack with Docker (optional)

```bash
cp .env.example .env          # root file: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
docker compose up --build     # API + PostgreSQL; the API runs alembic upgrade head first
```

### 4.6 Is it actually wired? — five checks

```bash
# 1. API alive
curl -s localhost:8000/api/v1/health
# 2. database reachable
curl -s localhost:8000/api/v1/health/ready          # {"status":"ready","database":"ok"}
# 3. seeded accounts work
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ali@ssuet.edu.pk","password":"Password123!"}' | head -c 120
# 4. admin console can see its backend (after npm run dev)
curl -s localhost:5173/api/v1/health                # proxies to the API → same JSON
# 5. phone reaches the backend (from another machine on the same Wi-Fi)
curl -s http://192.168.1.10:8000/api/v1/health
```

Then in the app: register → upload ID → verify it in the console → publish a ride → request
from a second account → accept → chat → complete → rate. If those pass, the system is
functional end to end.

---

## 5. Moves to production (the only differences that matter)

1. `ENVIRONMENT=production`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`.
2. `DATABASE_URL` → PostgreSQL, and run `alembic upgrade head`.
3. `JWT_SECRET_KEY` → 48+ random characters (placeholders are a **fatal** startup error).
4. `CORS_ORIGINS` and `ADMIN_WEB_URL` → your real HTTPS domain.
5. `MEDIA_ROOT` → a real volume that is in the backup set (`deploy/backup.sh`).
6. `MAINTENANCE_INTERVAL_MINUTES=0` and let **cron** run `scripts.expire_stale_rides` /
   `scripts.sweep_media` — keeps API workers stateless.
7. App: `EXPO_PUBLIC_API_URL=https://<domain>/api/v1`, then rebuild.
8. Start from `deploy/env.production.example` — it is the same list, pre-filled for a server.

Full procedure: [17-production-deployment.md](17-production-deployment.md); day-one
checklist and sign-off: [22-operations-handbook.md](22-operations-handbook.md).

---

## 5a. Known startup error: `ForwardRef('UploadFile')`

If `uvicorn app.main:app` dies at import with

```
fastapi.exceptions.FastAPIError: Invalid args for response field!
Hint: check that ForwardRef('UploadFile') is a valid Pydantic field type
```

you are on the **old dependency pins** (`fastapi 0.115.6`), from the first archive. It is a
packaging bug, not a code bug, and it only appears on a clean install — the development
host had newer versions and hid it.

```bash
pip install -U "fastapi==0.162.0"        # 30-second fix, restores the import
# or, the verified route: current requirements.txt + upgrade everything
pip install -U -r requirements.txt
```

Verified: upgrading `fastapi` alone makes the app import and serve (`/health` 200,
`/health/ready` ok) and keeps all 46 upload + profile-photo tests green. The full pin set in
the current `requirements.txt` is what the 422-test suite was run against on SQLite **and**
PostgreSQL.

## 5b. EAS build fails on a dynamic config (`app.config.ts`)

`eas init` / `eas build` prints

```
Warning: Your project uses dynamic app configuration, and the EAS project ID can't
automatically be added to it.
✖ Linking local project to EAS project …
Cannot automatically write to dynamic config at: app.config.ts
```

because the app describes itself in **`app.config.ts`** (needed for `EXPO_PUBLIC_*`), not in
`app.json`, and EAS refuses to rewrite TypeScript. The project id therefore lives in the
config itself:

```ts
extra: {
  eas: { projectId: process.env.EAS_PROJECT_ID ?? '11fd9726-022e-4f5a-8690-48deb063f925' },
},
```

Consequences worth knowing:

* `EAS_PROJECT_ID` in `.env` can still override it, for a fork on another account.
* **A cloud build never sees your local `.env`** (the file is git-ignored, and the build runs
  on Expo's machines). Anything the app needs at runtime has to be in `eas.json`
  → `build.<profile>.env`, which is why `EXPO_PUBLIC_API_URL` appears there.
* Release APKs **block cleartext `http://`**. Use the HTTPS deployment, or add
  `expo-build-properties` with `android.usesCleartextTraffic: true` for LAN testing.
* **A failed *Bundle JavaScript* phase is usually a fat upload.** EAS archives the *git
  tracked* files of the project directory. `git init` inside `mobile/` (without a
  `mobile/.gitignore`) therefore commits `node_modules` — and a 400 MB tree of
  Windows-installed native binaries (`lightningcss`, `esbuild`, `@swc`) is what the Linux
  builder then tries to bundle. Symptom: `Compressed project files … (74.8 MB)` followed by
  `🤖 Android build failed: Unknown error … Bundle JavaScript`.
  With the shipped `mobile/.gitignore`: **0.84 MB, 61 files**.
* The config's API fallback is build-aware: `EXPO_PUBLIC_API_URL` → else
  `https://rideshare.ssuet.edu.pk/api/v1` when `EAS_BUILD_PROFILE` is set (cloud build) →
  else `http://localhost:8000/api/v1` (local dev). A cloud build can therefore never ship an
  APK that points at `localhost`.
* Verify the config resolves before blaming the build:
  `node -e "console.log(require('@expo/config').getConfig(process.cwd(),{}).exp.extra)"`

## 5c. `Unable to resolve module @/theme` — the `@/` alias

The app imports its own modules as `@/theme`, `@/api/client`, … (164 times). That alias is
declared in `tsconfig.json` (`"paths": { "@/*": ["./src/*"] }`), and TypeScript resolves it for
type-checking. **Metro's** support for tsconfig paths is an Expo feature that can differ
between machines and, in practice, an EAS build failed on it while the same tree bundled here.

It is now belt-and-braces, so it cannot depend on toolchain behaviour:

* `babel.config.js` maps the alias with `babel-plugin-module-resolver` (`'@' → './src'`);
* `app.config.ts` sets `experiments.tsconfigPaths: true` as well;
* `tsconfig.json` keeps the paths for `tsc`.

Symptom if it breaks: `Bundling failed … Unable to resolve module @/theme from app/(auth)/_layout.tsx`.
Fix: `npm install` (the plugin is a devDependency), clear caches
(`Remove-Item -Recurse -Force .expo,node_modules\.cache,out`), rebuild with `--clear-cache`.
Verified: 1326 modules, 45 assets, bundle + full export both green.

## 5d. Pointing an installed APK at a different server (no rebuild)

`EXPO_PUBLIC_API_URL` is baked in at build time, so changing the server normally means
another 10-minute cloud build — painful when the "server" is a laptop whose Wi-Fi IP moves.

Testing builds (`EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`, already set in the `preview` profile)
render a **"Server (testing build)"** panel on the sign-in and sign-up screens:

* it shows the URL currently in effect, accepts `192.168.100.32:8000` as shorthand
  (normalised to `http://192.168.100.32:8000/api/v1`),
* **Save & test** stores it in the Android keystore, re-points axios and probes `/health`,
* **Reset** returns to the build-time value,
* the chat WebSocket follows automatically (it derives its URL from `api.defaults.baseURL`).

The same flag also switches on `expo-build-properties` →
`android.usesCleartextTraffic: true`, because Android blocks plain `http://` in release
builds. Verified: prebuild writes `android:usesCleartextTraffic="true"`, `tsc` clean,
bundle 1328 modules / 45 assets. Production builds leave the flag empty, so neither the
panel nor the cleartext allowance ships.

## 5e. Live end-to-end smoke test (HTTP, not in-process)

`backend/scripts/e2e_smoke.py` runs 31 checks against a **running** server, so it also proves
the network path a phone uses:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000          # terminal 1
.venv/bin/python scripts/e2e_smoke.py                    # terminal 2 → RESULT: ALL PASS
.venv/bin/python scripts/e2e_smoke.py http://192.168.100.32:8000/api/v1   # from the LAN URL
```

Business rules the journey proves: university emails auto-verify, a journey needs a geo point
matching its direction, `MAX_CONFIRMED_PASSENGERS` (default 1) caps seats, completion is
two-sided (driver **and** rider confirm), and a ride with a confirmed trip can no longer be edited.

## 5f. `database disk image is malformed` (SQLite dev database)

SQLite refuses to open `backend/app.db` at startup:

```
sqlite3.DatabaseError: database disk image is malformed
```

The file is a **development** database — it is rebuilt in seconds, no data of value is lost.
Startup now prints the exact steps instead of a 60-line traceback:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.reset_dev_db --yes   # deletes app.db, -wal, -shm
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
.\.venv\Scripts\python.exe -m scripts.seed                 # optional demo data
```

Likely causes, in order:

1. The server was killed (or the laptop slept) mid-write and a `-wal` file survived; deleting
   `app.db`, `app.db-wal` and `app.db-shm` together is what matters — a lone `app.db` deletion
   leaves a stale WAL behind.
2. The project lives inside a **OneDrive / Dropbox** folder that syncs while SQLite writes.
   Copy the project to `C:\dev\...` (or point `DATABASE_URL` outside the synced folder).
3. Two servers were running against the same file (`port already in use` plus a second start).

## 6. Mistakes that cost the most time

| Mistake | Symptom | Fix |
| --- | --- | --- |
| `EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1` on a phone | "Network error" on every screen | use the laptop's LAN IP; same Wi-Fi; allow port 8000 in the firewall |
| Editing `mobile/.env` while Metro is running | nothing changes | restart `expo start`; rebuild the APK for a build to pick it up |
| PostgreSQL without `alembic upgrade head` | `no such table: users` | run migrations (or use SQLite) |
| `MEDIA_ROOT` pointing somewhere unwritable | uploads 500 | use `./media` locally, a service-owned volume in production |
| Putting a secret in `EXPO_PUBLIC_*` / `VITE_*` | the secret is in the app bundle | server secrets belong only in `backend/.env` |
| Expecting an email that never arrives | `SMTP_HOST` empty → console log | copy the link from the backend terminal |
| Blank map | key expired / quota used | Admin → Map API → paste new key → Test (app falls back to OSM meanwhile) |
