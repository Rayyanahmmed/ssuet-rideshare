# 23 · Run it yourself — local setup & building the APK

Everything in this document was executed in the development sandbox, in this order, and
the two commands that matter most (`python -m scripts.seed` and
`npx expo export -p android`) were re-run while writing it. Where a step needs a tool this
sandbox does not have (Java/Android SDK, an EAS account), that is stated plainly.

> اردو میں خلاصہ: صرف **Python 3.11+, Node 20+** چاہیے۔ بیک اینڈ SQLite پر فوراً چل جاتا ہے
> (کوئی ڈیٹابیس سرور نہیں چاہیے)، ایڈمن کنسول `localhost:5173` پر، اور موبائل ایپ اسی
> Wi-Fi پر **Expo Go** سے چل جاتی ہے — APK بنانے کے لیے یا EAS (کلاؤڈ، مفت اکاؤنٹ) یا
> Android SDK + JDK 17 چاہیے۔

---

## 0. What you need

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.11+ (3.13 used here) | the API |
| Node.js | 20+ (22 used here) | console + mobile |
| Git | any | to clone |
| **Phone** | Android with **Expo Go** (free, Play Store) | to run the app without building anything |
| *(optional)* PostgreSQL 14+ | — | only if you want the production database locally |
| *(optional for APK)* | JDK 17 + Android SDK, **or** a free EAS account | see §5 |

Disk: ~700 MB with `node_modules` installed twice (mobile + console).

---

## 1. Backend — 3 minutes, no database server needed

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `backend/.env` and set **two** values:

```ini
DATABASE_URL=sqlite+pysqlite:///./ssuet_dev.db   # already the default in .env.example
JWT_SECRET_KEY=<paste 48+ random characters>      # REQUIRED — the app refuses to start without it
ADMIN_PASSWORD=Admin@SSUET2026                    # the console login you will use
```

> **Dependency pins matter here.** `requirements.txt` is pinned to the exact versions the
> 422-test suite and a clean-venv boot were verified against. An earlier pin set
> (`fastapi 0.115.6` + `python-multipart 0.0.20`) failed to import on a clean machine with
> `ForwardRef('UploadFile')` — the dev sandbox hid it by having newer versions installed.
> Change a pin → re-run `python -m pytest -q` and boot the API before shipping.

`.env.example` ships with **SQLite as the default** precisely so that these three minutes
are real: no database server, no migration step, tables created on first boot. Switching to
PostgreSQL later is uncommenting one line (§2).

Then:

```bash
python -m scripts.seed                # demo members, rides, trips, reports
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check it three ways:

| URL | Expected |
| --- | --- |
| <http://localhost:8000/api/v1/health> | `{"status":"ok", …}` |
| <http://localhost:8000/api/v1/health/ready> | `{"status":"ready"}` (database reachable) |
| <http://localhost:8000/docs> | Swagger UI with all 99 routes |

**Seeded accounts** (password `Password123!` unless noted):

| Email | Who |
| --- | --- |
| `ali@ssuet.edu.pk` | student, drives a Corolla, 3 published rides |
| `fatima@ssuet.edu.pk` | student, matched trip with chat, pending request |
| `ahmed@ssuet.edu.pk` | student, one completed trip, rated 5.0 |
| `drfaheem@ssuet.edu.pk` | teacher, free morning rides |
| `usman@ssuet.edu.pk` | suspended account (to see the admin path) |
| `admin@example.com` | **administrator console** — password `Admin@SSUET2026` |

> `AUTO_CREATE_TABLES` is on for SQLite, so there is no migration step. **With PostgreSQL
> you must run `alembic upgrade head` before starting** — that is the one difference that
> bites people (see §2).

### Verified on a clean copy

This exact path was run against a fresh unzip of the repository (empty directory, no
existing database) while writing this guide:

```
$ python -m scripts.seed          → "Created 1 matched trip (with chat), 1 completed trip (with reviews), 1 report"
$ uvicorn app.main:app --port 8000
  GET /api/v1/health        → 200 · {"status":"ok"}
  GET /api/v1/health/ready  → {"status":"ready","database":"ok"}
  GET /docs                 → 200
  login ali@ssuet.edu.pk    → access token 287 chars
  GET /rides?limit=3        → 3 rides
  GET /admin/health         → status ok · dialect sqlite · members 11
```

**Two warnings on a brand-new database are normal**, and both are the health panel doing its
job: *"no alembic_version row (created by AUTO_CREATE_TABLES?)"* — true, because SQLite
created the tables directly; and *"housekeeping has not run yet"* — true until the first
15-minute cycle. Neither appears on a PostgreSQL install that ran `alembic upgrade head`.

---

## 2. Backend on PostgreSQL (optional, matches production)

```bash
createdb ssuet_rideshare
cd backend
DATABASE_URL="postgresql+psycopg://<user>:<pass>@localhost:5432/ssuet_rideshare" alembic upgrade head
DATABASE_URL="…" python -m scripts.seed
DATABASE_URL="…" uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or the same thing in containers: `docker compose up --build` from the repo root
([`docker-compose.yml`](../docker-compose.yml) — includes the database; the API container
migrates before it starts). Docker was **not** exercised in the sandbox, so treat it as
"should work", not "verified here".

---

## 3. Admin console — 1 minute

```bash
cd admin-dashboard
npm install
npm run dev            # → http://localhost:5173
```

Sign in with `admin@example.com` / `Admin@SSUET2026`. The dev server proxies `/api` to
`http://127.0.0.1:8000` (see `vite.config.ts`), so start the backend first. To point it
elsewhere: `VITE_PROXY_TARGET=http://192.168.1.10:8000 npm run dev`.

Production build: `npm run build` → `dist/` (796 K, static files, deploy behind any web server).

---

## 4. Mobile app — run it on your phone in 2 minutes (no build)

This is the fastest way to see the real app: no Android SDK, no signing, no APK.

```bash
cd mobile
npm install
npx expo start --lan
```

1. Install **Expo Go** on the Android phone (Play Store).
2. Scan the QR code from the terminal. The app opens.
3. **Point the app at your computer** — this is the step everyone misses:
   ```bash
   # find your LAN IP first:  ipconfig (Windows) · ifconfig / ip addr (macOS/Linux)
   EXPO_PUBLIC_API_URL="http://192.168.1.10:8000/api/v1" npx expo start --lan
   ```
   Phone and laptop must be on the **same Wi-Fi**, and the backend must be bound to
   `0.0.0.0` (the command in §1 already is). `localhost` on the phone means *the phone*,
   which is why a wrong URL shows "Network error" and nothing else.
4. Windows Firewall may block port 8000 — allow it, or the phone will time out.

---

## 5. Build the APK

### Option A — EAS Build (cloud, no Android SDK, free tier)

```bash
cd mobile
npm install -g eas-cli      # or use: npx eas-cli@latest
eas login                   # free Expo account
eas build -p android --profile preview
```

* `preview` profile → an installable **APK**, link printed in the terminal and on
  expo.dev. Download it on the phone and install (allow "install from unknown sources").
* `production` profile → an **AAB** for the Play Store (`npm run build:production`).
* Set the API URL at build time, or the APK will point at nothing:
  ```bash
  EXPO_PUBLIC_API_URL="http://192.168.1.10:8000/api/v1" eas build -p android --profile preview
  ```
  For a real pilot use the public URL: `https://rideshare.ssuet.edu.pk/api/v1`.

Cloud builds take 5–15 minutes and need no local Android tooling — this is what the
project's own release notes assume (see doc 12 §build).

### Option B — build the APK locally (no account, full control)

Needs **JDK 17** and the **Android SDK** (platform 34+, build-tools). Then:

```bash
cd mobile
npm install
npx expo prebuild -p android            # generates ./android from app.config.ts
cd android
./gradlew assembleRelease               # Windows: gradlew.bat assembleRelease
# APK → android/app/build/outputs/apk/release/app-release.apk
```

Notes that save an hour:

* `assembleRelease` without a keystore signs with a **debug** key — fine for testing on
  your own phone, **not** for distribution. Configure `android/app/build.gradle` with your
  keystore before publishing.
* The first Gradle run downloads ~1 GB. Do it on a good connection.
* Prebuild creates files that are **not** in the repo (`android/` is git-ignored): the app
  is described by `app.config.ts` + `eas.json`, so re-running prebuild is always safe.
* This sandbox has **no Java/Android SDK**, so Option B was not executed here — the
  project's Android artefact was verified as a JS bundle instead
  (`npx expo export -p android` → 4.21 MB HBC), which proves the app compiles, not that
  Gradle runs on your machine.

---

## 6. What to test first (a 10-minute smoke path)

1. Console → *Users* → verify an unverified member (use `usman@`? no — he is suspended;
   use a fresh account you register in the app).
2. App → register → submit your student ID (photo upload) → see it appear in
   console *Verification Requests* → verify it → the app unlocks publishing.
3. App → publish a journey → from a second phone/account request a seat → accept →
   chat → start → complete → rate each other.
4. Console → *Reports & complaints* → file a report from the app against a photo → handle
   it, tick "Also remove the photo".
5. Backend → `GET /api/v1/admin/health` (admin token) → `status: ok`, `warnings: []`.

If all five work, the whole product is wired end to end on your machine.

---

## 7. Common failures, in the order they happen

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: app` | ran uvicorn from the repo root | `cd backend` first |
| `no such table: users` | PostgreSQL without migrations (SQLite creates its own) | `alembic upgrade head` |
| Console loads but every list is empty + "401" | backend not running, or wrong port | start uvicorn on :8000; check the proxy line in `vite.config.ts` |
| App shows "Network error" | `EXPO_PUBLIC_API_URL` wrong — usually `localhost` instead of the PC's LAN IP | see §4 step 3 |
| App cannot upload a photo | Android permission denied | allow Photos in app settings |
| `npm install` ERESOLVE errors | peer-dependency churn in React 19 | `npm install --legacy-peer-deps` (the repo pins `react-dom@19.1.0`) |
| `eas build` asks for a keystore | first build only | let EAS generate one, keep the credentials |
| Ports 5173/8000 already in use | an old process | Windows: `netstat -ano \| findstr :5173`; macOS/Linux: `lsof -i :5173` |

---

## 8. The honest limits of running it "locally"

* **Push notifications need a project id.** Without `EXPO_PUSH_ENABLED` + an Expo project,
  notifications appear **inside** the app (the bell list) but no system notification pops.
* **Maps need no key at all.** The app draws a WebView map from OpenStreetMap tiles that the
  backend proxies, so a fresh install has a working map on day one. Want Geoapify/MapTiler
  instead (nicer styles, higher limits)? Paste the key in the console → **Map API**; when it
  expires, paste the new one there. The app never needs a rebuild for a key change.
* **Email verification needs SMTP.** Without it, verification emails are **logged to the
  console** (`DEV EMAIL …`), which is enough to copy the link/token while developing.
* **Map tiles travel through your laptop** while testing over LAN: the phone asks
  `http://192.168.100.32:8000/api/v1/maps/tiles/...` and the backend fetches them. That is
  deliberate — it is what keeps the key on the server. If the backend stops, the map stops;
  the area list still works.
* **`localhost` vs LAN** — the single most common wasted hour. Phone ≠ laptop.
* **The APK you build is not on the Play Store** and is not signed for distribution; it is
  a test build, which is exactly what it is for.
