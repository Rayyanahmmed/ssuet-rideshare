# 25 · Deployment — every command, in order

A single linear sheet for putting SSUET RideShare on a **fresh Ubuntu 22.04 / 24.04 VPS**.
Copy the blocks in order; each phase ends with a **verify** line, so a failure is caught at
the phase that caused it instead of three phases later.

> Scope honesty: phases 1–3 and 7 (systemd) cannot run in the development sandbox (no PID 1
> systemd, no root provisioning), so those lines are the standard commands, not executed
> here. Everything that *could* run here has been run: the gunicorn command line, nginx
> config, PostgreSQL parity, backups/restore, and the 17-check smoke test. See
> [17-production-deployment.md](17-production-deployment.md) §4 and §8.

Assumed: 2 vCPU / 2 GB RAM VPS, domain **`rideshare.ssuet.edu.pk`**, sudo user.
Replace the domain everywhere if yours differs (`sed -i 's/rideshare.ssuet.edu.pk/your.domain/g'`).

---

## Phase 0 — before you touch the server

On your laptop:

```bash
# the archive you were given (or: git clone <repo>)
sha256sum SSUET-RideShare-v1.0.0.zip

# DNS must already resolve to the VPS — TLS will fail otherwise
dig +short rideshare.ssuet.edu.pk
```

**Do this first:** DNS `A` record → VPS IPv4. Certbot needs it to answer the HTTP challenge.

---

## Phase 1 — base system

```bash
ssh root@<VPS_IP>

apt update && apt upgrade -y
apt install -y python3 python3-venv python3-dev build-essential libpq-dev \
               postgresql postgresql-contrib nginx git curl unzip \
               certbot python3-certbot-nginx ufw

# a predictable clock matters for JWT expiry, backups and log correlation
timedatectl set-timezone Asia/Karachi

# firewall: only SSH and HTTP(S) are public. 8000/8010/5432 stay closed.
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```

**Verify:** `python3 --version` (3.10+), `psql --version`, `nginx -v`, `ufw status` shows 22/80/443.

---

## Phase 2 — service user and directories

```bash
adduser --system --group --home /srv/ssuet-rideshare --shell /usr/sbin/nologin ssuet
mkdir -p /srv/ssuet-rideshare /var/lib/ssuet-rideshare/media /etc/ssuet-rideshare \
         /var/backups/ssuet-rideshare /var/www/certbot
chown -R ssuet:ssuet /srv/ssuet-rideshare /var/lib/ssuet-rideshare /var/backups/ssuet-rideshare
chmod 755 /var/www/certbot
```

**Verify:** `id ssuet` and `ls -ld /var/lib/ssuet-rideshare/media` (owner `ssuet`).

---

## Phase 3 — PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE ssuet LOGIN PASSWORD 'CHANGE_ME_DB_PASSWORD';
CREATE DATABASE ssuet_rideshare OWNER ssuet;
SQL

# prove the credentials work before the app tries them
PGPASSWORD='CHANGE_ME_DB_PASSWORD' psql -h 127.0.0.1 -U ssuet -d ssuet_rideshare -c 'select version();'
```

**Verify:** the `select version()` line prints. If it fails, the app will fail too — fix here.

---

## Phase 4 — deploy the code

From your laptop:

```bash
scp SSUET-RideShare-v1.0.0.zip root@<VPS_IP>:/tmp/
```

On the server:

```bash
cd /tmp
unzip -q SSUET-RideShare-v1.0.0.zip
rsync -a /tmp/SSUET-RideShare/ /srv/ssuet-rideshare/     # first install: copy everything
chown -R ssuet:ssuet /srv/ssuet-rideshare

# Python dependencies (production set: no pytest, no dev tools)
sudo -u ssuet python3 -m venv /srv/ssuet-rideshare/backend/.venv
sudo -u ssuet /srv/ssuet-rideshare/backend/.venv/bin/pip install --upgrade pip
sudo -u ssuet /srv/ssuet-rideshare/backend/.venv/bin/pip install \
     -r /srv/ssuet-rideshare/backend/requirements-prod.txt
```

**Verify:**
```bash
sudo -u ssuet /srv/ssuet-rideshare/backend/.venv/bin/python -c "import fastapi, uvicorn, psycopg; print('deps ok')"
```

> To update later, replace Phase 4 with: `git -C /srv/ssuet-rideshare pull` (or a new rsync) →
> `pip install -r requirements-prod.txt` → Phase 6 → `systemctl restart ssuet-api` →
> Phase 12. That is the whole release procedure ([22-operations-handbook.md](22-operations-handbook.md) §6).

---

## Phase 5 — environment file

```bash
cp /srv/ssuet-rideshare/deploy/env.production.example /etc/ssuet-rideshare/api.env

# a real secret — never a placeholder: production startup refuses those
python3 -c "import secrets;print(secrets.token_urlsafe(48))"

nano /etc/ssuet-rideshare/api.env
```

Fill in, at minimum:

```ini
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql+psycopg://ssuet:CHANGE_ME_DB_PASSWORD@127.0.0.1:5432/ssuet_rideshare
AUTO_CREATE_TABLES=false
JWT_SECRET_KEY=<the 48-byte secret you just generated>
ADMIN_EMAIL=transport@ssuet.edu.pk
ADMIN_PASSWORD=<strong password for the console>
CORS_ORIGINS=https://rideshare.ssuet.edu.pk
ADMIN_WEB_URL=https://rideshare.ssuet.edu.pk
MEDIA_ROOT=/var/lib/ssuet-rideshare/media
MAINTENANCE_INTERVAL_MINUTES=0        # cron does the housekeeping instead
# optional, degrade gracefully when empty
SMTP_HOST=
MAP_PROVIDER=osm
GEOAPIFY_API_KEY=   # optional; prefer setting it in Admin → Map API
EXPO_ACCESS_TOKEN=
```

Then lock it down:

```bash
chown root:ssuet /etc/ssuet-rideshare/api.env
chmod 640 /etc/ssuet-rideshare/api.env
```

**Verify:** `sudo -u ssuet grep -c . /etc/ssuet-rideshare/api.env` works (the service can read it) and `stat -c '%a %U:%G' /etc/ssuet-rideshare/api.env` → `640 root:ssuet`.

---

## Phase 6 — database schema and the first administrator

```bash
cd /srv/ssuet-rideshare/backend

# load the env file into this shell (same values the service will see)
set -a; . /etc/ssuet-rideshare/api.env; set +a

sudo -u ssuet --preserve-env=DATABASE_URL,ENVIRONMENT,JWT_SECRET_KEY,ADMIN_EMAIL,ADMIN_PASSWORD \
  .venv/bin/alembic upgrade head

# migrations are the only path — this must say "No new upgrade operations detected"
sudo -u ssuet --preserve-env=DATABASE_URL .venv/bin/alembic check
```

First administrator: setting `ADMIN_BOOTSTRAP_ENABLED=true` in the env file creates the
account **once**, on the next start (Phase 7). After you have logged in successfully, set it
to `false` and restart:

```bash
sed -i 's/^ADMIN_BOOTSTRAP_ENABLED=true/ADMIN_BOOTSTRAP_ENABLED=false/' /etc/ssuet-rideshare/api.env
```

**Demo data is *not* deployed.** `python -m scripts.seed` is for local work only; on
production, members register through the app and are verified in the console.

**Verify:** `sudo -u postgres psql -d ssuet_rideshare -c '\dt' | head` lists the tables.

---

## Phase 7 — the API as a service

```bash
cp /srv/ssuet-rideshare/deploy/ssuet-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ssuet-api
systemctl status ssuet-api --no-pager
journalctl -u ssuet-api -n 40 --no-pager
```

**Verify (the real test — the API answers on its private port):**

```bash
curl -s http://127.0.0.1:8010/api/v1/health        # {"status":"ok", ...}
curl -s http://127.0.0.1:8010/api/v1/health/ready  # {"status":"ready","database":"ok"}
```

Restart / stop / logs:

```bash
systemctl restart ssuet-api
systemctl stop ssuet-api
journalctl -u ssuet-api -f
```

---

## Phase 8 — build the admin console

Either build on the server (simplest) or build locally and copy `dist/`.

```bash
# on the server
apt install -y nodejs npm          # Node 20+; use nodesource if apt ships an old one
cd /srv/ssuet-rideshare/admin-dashboard
sudo -u ssuet npm ci --omit=dev || sudo -u ssuet npm ci
sudo -u ssuet npm run build        # → dist/  (~800 KB)

# nginx must be able to read it, and only that
chmod -R a+rX /srv/ssuet-rideshare/admin-dashboard/dist
```

The console talks to the API on the **same origin** (`/api/v1`), so
`VITE_API_BASE_URL` stays empty — no CORS, no second certificate.

> Local-build alternative: `npm run build` on your laptop, then
> `rsync -a admin-dashboard/dist/ root@<VPS_IP>:/srv/ssuet-rideshare/admin-dashboard/dist/`.

**Verify:** `ls /srv/ssuet-rideshare/admin-dashboard/dist/index.html`.

---

## Phase 9 — nginx and TLS

```bash
cp /srv/ssuet-rideshare/deploy/nginx/ssuet-rideshare.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/ssuet-rideshare.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# HTTPS blocks reference certificates that do not exist yet → expected to fail on the
# first pass. Comment them, start HTTP-only, get the certificate, then uncomment.
nginx -t
systemctl reload nginx

# certificate (the shipped config already serves the ACME challenge from /var/www/certbot)
certbot --nginx -d rideshare.ssuet.edu.pk --agree-tos -m admin@ssuet.edu.pk --redirect
nginx -t && systemctl reload nginx
```

**Verify:**

```bash
curl -sI https://rideshare.ssuet.edu.pk/api/v1/health | head -1     # HTTP/2 200
curl -sI https://rideshare.ssuet.edu.pk | grep -i strict-transport  # security headers
curl -sI http://rideshare.ssuet.edu.pk | head -1                    # 301 → https
```

---

## Phase 10 — housekeeping, backups, monitoring (cron)

```bash
sudo -u ssuet crontab -e
```

```cron
# API housekeeping (MAINTENANCE_INTERVAL_MINUTES=0 keeps workers stateless)
*/15 * * * * cd /srv/ssuet-rideshare/backend && ./.venv/bin/python -m scripts.expire_stale_rides

# database + uploaded documents, kept 14 days
15 3 * * * /srv/ssuet-rideshare/deploy/backup.sh >> /var/log/ssuet-backup.log 2>&1

# unreferenced uploads older than 7 days
30 3 * * * cd /srv/ssuet-rideshare/backend && ./.venv/bin/python -m scripts.sweep_media

# health watcher (alerts on failure; install the systemd timer instead if you prefer)
*/5 * * * * /srv/ssuet-rideshare/deploy/monitor.sh >> /var/log/ssuet-monitor.log 2>&1
```

Prove the backup **and** the restore *now*, not during an incident:

```bash
# 1. a backup is a timestamped DIRECTORY (not a .tar.gz): dump + media + manifest + checksums
/srv/ssuet-rideshare/deploy/backup.sh
ls -lh /var/backups/ssuet-rideshare/ | tail -3
cat /var/backups/ssuet-rideshare/<STAMP>/MANIFEST
tar -tzf /var/backups/ssuet-rideshare/<STAMP>/media.tar.gz | head

# 2. the restore rehearsal. restore.sh takes the backup DIRECTORY, verifies SHA256SUMS,
#    asks you to type RESTORE, and refuses to run while ssuet-api is active.
sudo systemctl stop ssuet-api
/srv/ssuet-rideshare/deploy/restore.sh /var/backups/ssuet-rideshare/<STAMP>
sudo systemctl start ssuet-api
./deploy/smoke.sh https://rideshare.ssuet.edu.pk
```

Verified here end to end on a copy of the development stack (SQLite + 11 uploaded documents):
`backup → database.sqlite3 636K · media.tar.gz 128K (11 files) → MANIFEST + SHA256SUMS →
deleted both → restore → "media restored (11 files)", 15 rows back in `users`; and with a
live service the script correctly refused: *"ssuet-api is running. Stop it first."*
SQLite backs up with `sqlite3 .backup` (consistent copy); PostgreSQL with `pg_dump --format custom`.

**Verify:** `MANIFEST`, `SHA256SUMS` and either `database.dump` (PostgreSQL) or
`database.sqlite3` (SQLite) exist, and `media.tar.gz` is not empty.

---

## Phase 11 — release the app

```bash
cd /srv/ssuet-rideshare/mobile        # or on your laptop
cp .env.example .env
```

```ini
EXPO_PUBLIC_API_URL=https://rideshare.ssuet.edu.pk/api/v1
EAS_PROJECT_ID=<from `eas init`>
```

```bash
npm install
npx eas-cli@latest login
npx eas-cli@latest build -p android --profile production     # AAB for Play Store
# or, for a directly installable file:
npx eas-cli@latest build -p android --profile preview        # APK
```

Local build instead (JDK 17 + Android SDK): `npx expo prebuild -p android && cd android && ./gradlew assembleRelease`.

**Verify:** install the APK, log in, publish a ride — i.e. the phone reaches
`https://rideshare.ssuet.edu.pk/api/v1` with no network error.

---

## Phase 12 — post-deploy verification (never skip)

```bash
cd /srv/ssuet-rideshare
./deploy/smoke.sh https://rideshare.ssuet.edu.pk        # expects: 17 passed, 0 failed

# with a real login included
SMOKE_EMAIL=transport@ssuet.edu.pk SMOKE_PASSWORD='<password>' \
  ./deploy/smoke.sh https://rideshare.ssuet.edu.pk
```

Expected tail:

```
17 passed, 0 failed
```

Then, by hand: open the console in a browser and sign in; open `/admin/health` (admin token)
and confirm `status: ok`, no warnings; install the app and complete one full journey
(register → verify → publish → request → accept → chat → complete → rate).

Record it in the handbook sign-off page ([doc 22](22-operations-handbook.md) §11) — that is
the release evidence the SSUET office expects.

---

## Rollback in one minute

```bash
# code: return to the previous release
git -C /srv/ssuet-rideshare log --oneline -3
git -C /srv/ssuet-rideshare checkout <previous-tag-or-commit>
sudo -u ssuet /srv/ssuet-rideshare/backend/.venv/bin/pip install -r /srv/ssuet-rideshare/backend/requirements-prod.txt
systemctl restart ssuet-api
./deploy/smoke.sh https://rideshare.ssuet.edu.pk

# database: if the new release migrated the schema and must be undone
set -a; . /etc/ssuet-rideshare/api.env; set +a
cd /srv/ssuet-rideshare/backend && sudo -u ssuet --preserve-env=DATABASE_URL .venv/bin/alembic downgrade -1
```

If the schema change cannot be reversed safely, restore the last backup instead
(`deploy/restore.sh`) — that is why Phase 10 is not optional.

---

## If it breaks — the four failures that cover most of it

| Symptom | Check | Fix |
| --- | --- | --- |
| `502 Bad Gateway` from nginx | `journalctl -u ssuet-api -n 50` | service down: env error, DB unreachable, or an unwritable `MEDIA_ROOT` |
| `400 Bad Request` from the API behind nginx | `TrustedHost` / proxy headers | confirm the unit's `--forwarded-allow-ips 127.0.0.1` is intact |
| Certificate not issued | `dig +short <domain>` | DNS not pointing at the VPS yet; retry `certbot --nginx -d <domain>` |
| Console loads, all calls 401/404 | `curl https://<domain>/api/v1/health` | wrong `VITE_API_BASE_URL` or a stale `dist/` built against another origin |

Logs to keep open: `journalctl -u ssuet-api -f` · `/var/log/nginx/error.log` ·
`/var/log/ssuet-backup.log` · `/var/log/ssuet-monitor.log`.
