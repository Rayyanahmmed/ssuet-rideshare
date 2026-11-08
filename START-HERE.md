# START HERE — unzip, then run these commands

Step-by-step for **your own laptop**, after unzipping `SSUET-RideShare-v1.0.0.zip`.
Windows commands first, macOS/Linux variations in the grey boxes.

Total time: **~10 minutes** (most of it `pip install` / `npm install` downloading).

---

## What you need

| | Version | Check with |
| --- | --- | --- |
| Python | 3.11 or newer | `python --version` |
| Node.js | 20 or newer | `node --version` |
| *(optional)* phone with **Expo Go** | Play Store, free | — to run the app without building anything |

You need **3 terminals** open (backend, console, mobile). Nothing else — the database is a
file that creates itself.

---

## Step 1 — unzip and open a terminal in the folder

```
Right-click the zip → Extract All →  SSUET-RideShare\
```

Then, in File Explorer, open that folder and type `cmd` in the address bar + Enter
(or on macOS/Linux: `cd ~/Downloads/SSUET-RideShare`).

You should see `README.md`, `backend\`, `mobile\`, `admin-dashboard\`, `documentation\`.

---

## Step 2 — TERMINAL 1: the backend

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

Takes 1–3 minutes. When it finishes your prompt shows `(.venv)`.

Now create the config:

```bat
copy .env.example .env
```

Open `backend\.env` in Notepad and change **two** lines:

```ini
JWT_SECRET_KEY=PASTE_A_LONG_RANDOM_STRING_HERE
ADMIN_PASSWORD=Admin@SSUET2026
```

Generate the random string with:

```bat
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Everything else in that file is already correct — **`DATABASE_URL` is SQLite**, a single file,
no database server to install.

Load demo data (members, rides, trips, chat, reports):

```bat
python -m scripts.seed
```

```
Seed complete.
Login example: ali@ssuet.edu.pk / Password123!
```

Start the API **and leave this window running**:

```bat
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Check it:** open <http://localhost:8000/docs> → Swagger UI with 99 routes. ✅

---

## Step 3 — TERMINAL 2: the admin console

New terminal, from the project folder:

```bat
cd admin-dashboard
npm install
npm run dev
```

Expected:

```
  ➜  Local:   http://localhost:5173/
```

**Check it:** open <http://localhost:5173> → sign in with

```
admin@example.com  /  Admin@SSUET2026        (the ADMIN_PASSWORD you set in step 2)
```

You should land on the dashboard: users, rides, verification queue, reports, health. ✅

> The console proxies `/api` to `127.0.0.1:8000`, so the backend must already be running.

---

## Step 4 — TERMINAL 3: the app on your phone (no build)

New terminal, from the project folder:

```bat
cd mobile
npm install
```

Find your computer's Wi-Fi IP:

```bat
ipconfig
```

Look for **IPv4 Address** under your Wi-Fi adapter, e.g. `192.168.1.10`.

Put it in `mobile\.env` (create the file by copying `.env.example`):

```bat
copy .env.example .env
```

```ini
EXPO_PUBLIC_API_URL=http://192.168.1.10:8000/api/v1
```

Then:

```bat
npx expo start --lan
```

* Install **Expo Go** on the Android phone (Play Store).
* Phone and laptop on the **same Wi-Fi**.
* Scan the QR code that appears in the terminal.

**Check it:** the app opens → log in as `ali@ssuet.edu.pk` / `Password123!` → Explore shows
rides. ✅

> The classic mistake: leaving `localhost` in `EXPO_PUBLIC_API_URL`. On a phone `localhost`
> means *the phone*, so every screen says "Network error". Use the LAN IP.
> If it still fails, allow **port 8000** in Windows Firewall (or turn off the public-network block).

---

## Step 5 — prove the whole thing works (5 minutes)

1. In the app: **register** a new account with any `@ssuet.edu.pk` address.
2. Upload a student card photo when asked.
3. Console → **Verification requests** → open your account → **Verify**.
4. In the app: publish a ride (pickup area, time, seats).
5. Log in on a second device/account → find that ride → **Request seat**.
6. Driver accepts → open the trip → send a chat message → **Start trip** → **Complete**.
7. Both accounts rate each other.

If those work, every layer (auth, media, rides, requests, chat, notifications, trips,
reviews, admin) is wired on your machine.

---

## Step 6 — (optional) build the APK

**Cloud, no Android SDK needed** (free Expo account):

```bat
cd mobile
npx eas-cli@latest login
npx eas-cli@latest build -p android --profile preview
```

Download link appears in the terminal / on expo.dev → install the APK on the phone.

Four things this archive already takes care of, which EAS normally asks you for:

1. **Git repo** — EAS wants one. `git init` inside `mobile/` and commit: that is all it needs.
2. **`extra.eas.projectId`** — the project
   `@rayyanahmedkhan/ssuet-rideshare` is already wired into `app.config.ts` as a default, so
   you do **not** have to paste it by hand (EAS cannot edit a *dynamic* config itself).
3. **The API URL the APK talks to** — a cloud build never reads your local `.env`. It comes
   from `eas.json`:
   ```json
   "env": { "EXPO_PUBLIC_API_URL": "https://ssuet-rideshare-api.onrender.com/api/v1" }
   ```
   Both `preview` and `production` point at the deployed server, so a built APK works on any
   network. To talk to your laptop instead, put
   `http://<LAN-IP>:8000/api/v1` there **and** see the cleartext note below.
4. **The upload must be ~1 MB, not 75 MB.** `mobile/.gitignore` keeps `node_modules` out of
   git, and EAS only uploads what git tracks. If the build log says
   `Compressed project files … (74.8 MB)` and then fails in *Bundle JavaScript*, it shipped a
   Windows `node_modules` to a Linux builder. Fix once:
   ```powershell
   git rm -r --cached node_modules | Out-Null
   # add the .gitignore from this archive (mobile/.gitignore), then:
   git add .gitignore
   git commit -m "chore: ignore node_modules so EAS uploads source only"
   ```
   Next upload: `0.84 MB, 61 files`.
5. **Android blocks plain `http://`** in release APKs. `https://…` needs nothing extra; if you
   must use `http://192.168.x.x`, add the `expo-build-properties` plugin with
   `android.usesCleartextTraffic: true`, otherwise the app says "Network error" no matter
   what.

**Locally** (needs JDK 17 + Android SDK):

```bat
npx expo prebuild -p android
cd android
gradlew.bat assembleRelease
```

APK: `android\app\build\outputs\apk\release\app-release.apk`

> For a build, the URL must be reachable by the phone — for a real pilot use your
> deployed API address (see `documentation/27-deploy-vercel-render.md`), not a LAN IP.

---

## Stopping and restarting later

Stop: `Ctrl+C` in each of the 3 terminals.

Start again (no reinstall needed):

```bat
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
cd admin-dashboard && npm run dev
cd mobile && npx expo start --lan
```

Your data stays in `backend\ssuet_dev.db`. To start over: delete that file and re-run
`python -m scripts.seed`.

---

## If something goes wrong

| What you see | Cause | Fix |
| --- | --- | --- |
| `Unable to resolve module @/theme` (or any `@/…`) while bundling | the TypeScript path alias `@/*` → `./src/*` is not being honoured on that machine / on EAS | `mobile/babel.config.js` now maps it with `babel-plugin-module-resolver` (and `experiments.tsconfigPaths: true`); run `npm install`, then rebuild |
| `FastAPIError: Invalid args for response field! … ForwardRef('UploadFile')` | you installed from the **earlier** archive (old pins) | `pip install -U "fastapi==0.162.0"`, or better: replace `requirements.txt` with the one in the current zip and run `pip install -U -r requirements.txt` |
| `'python' is not recognized` | Python not on PATH | reinstall Python with "Add to PATH", or use `py -3` |
| `activate` blocked in PowerShell | execution policy | use `cmd` instead, or `Set-ExecutionPolicy -Scope Process RemoteSigned` |
| `ModuleNotFoundError: No module named 'app'` | running from the wrong folder | `cd backend` first |
| `ModuleNotFoundError: No module named 'fastapi'` | venv not activated | `.venv\Scripts\activate`, then re-run pip |
| Port 8000 / 5173 already in use | old process still running | `netstat -ano \| findstr :8000` → `taskkill /PID <pid> /F` |
| App: "Network error" everywhere | `EXPO_PUBLIC_API_URL` wrong | LAN IP, same Wi-Fi, firewall open |
| Console shows 401 / empty lists | backend not running | check Terminal 1, open <http://localhost:8000/api/v1/health> |
| `429 Too Many Requests` | rate limiter (5 logins/min) | wait 60 seconds — it is working as designed |
| `npm install` ERESOLVE | peer deps | `npm install --legacy-peer-deps` |
| Emails never arrive | no SMTP configured | the link is printed in Terminal 1: `DEV EMAIL …` |

Deeper troubleshooting: [documentation/23-run-it-yourself.md](documentation/23-run-it-yourself.md)
(§7) and every variable explained in
[documentation/24-environment-and-commands.md](documentation/24-environment-and-commands.md).

---

## Verified — this exact path was executed

Against a fresh unzip of this archive, in a clean virtual environment built from
`requirements.txt`:

```
pip install -r requirements.txt     → 17 pinned packages, no resolver conflicts
python -m scripts.seed              → "Seed complete."
uvicorn app.main:app                → GET /health 200 · /health/ready {"status":"ready"}
                                      GET /docs 200 · login (member) 200 · login (admin) 200
python -m pytest -q                 → 422 passed on SQLite
python -m pytest -q (PostgreSQL 17) → 422 passed
pip install -r requirements-prod.txt + gunicorn (the systemd unit's exact command line)
                                    → /health 200 · /health/ready ok · login 200
```

> Dependency pins in `requirements.txt` were corrected while writing this guide: the
> previously pinned `fastapi 0.115.6` + `python-multipart 0.0.20` combination **failed to
> import on a clean machine** (`ForwardRef('UploadFile')`), even though the development
> sandbox — which had newer versions installed — looked fine. Every pin is now the version
> the 422-test suite actually ran against, on SQLite **and** PostgreSQL.

## Verification suite (run before every demo)

| # | Command | Expected |
|---|---|---|
| 1 | `cd backend && .venv/bin/python -m pytest -q` | 494 passed |
| 2 | `PYTHONPATH=. .venv/bin/python scripts/check_contracts.py` | `99/99` routes, ✓ |
| 3 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` (other terminal) | `GET /api/v1/health` → `{"status":"ok"}` |
| 4 | `.venv/bin/python scripts/e2e_smoke.py http://127.0.0.1:8000/api/v1` | `RESULT: ALL PASS` (31 checks) |
| 5 | `cd mobile && npx tsc --noEmit` | no output, exit 0 |
| 6 | `npx expo-doctor` | `18/18 checks passed` |
| 7 | `npx expo export:embed --platform android --dev false --minify true --entry-file node_modules/expo-router/entry.js --bundle-output out\index.bundle --assets-dest out\assets --reset-cache` | `1330 modules`, `45 assets`, `Done` |
| 8 | `cd admin-dashboard && npx tsc --noEmit && npx vite build` | `✓ built` |

`scripts/e2e_smoke.py` drives the real HTTP journey the phone performs — register → login →
refresh → profile → vehicle → publish ride → book → accept → start → complete (both sides) →
review → notifications → logout. Point it at the LAN URL (`http://192.168.100.32:8000/api/v1`)
to prove the phone's network path *before* building an APK.
