# 17 · Phase 11 — production deployment & CI

**Status:** complete and *rehearsed*, not just written. The stack in `deploy/` was run
here: nginx terminating TLS with the shipped config, gunicorn supervising three uvicorn
workers in `ENVIRONMENT=production`, the suite executed against **PostgreSQL 17**, and
the shipped smoke test reporting **17/17**.

What is *not* in this phase: a real domain, a real certificate and a real phone. Those
need the university's DNS and an Expo account — see §8 for the exact handover steps.

---

## 1. Why this came before more features

Ten phases produced software that only ever ran on a laptop: `uvicorn --reload` against
SQLite, no TLS, no supervisor, no backup, and no way for anyone but the author to know it
still worked. A feature an operator cannot deploy is a demo, not a product.

## 2. What shipped

| Piece | File | Why it exists |
| --- | --- | --- |
| Environment contract | `deploy/env.production.example` | every setting production needs, with the secrets called out; the app **refuses to start** with a weak JWT secret in production |
| Process supervision | `deploy/ssuet-api.service` | gunicorn + `UvicornWorker` (async, so the chat socket keeps working), auto-restart, hardened systemd (`ProtectSystem=strict`, `ReadWritePaths` = media only) |
| Reverse proxy | `deploy/nginx/ssuet-rideshare.conf` | one origin for console + API + uploads + WebSocket; TLS + HSTS + CSP; 6 MB body cap; edge rate limits; SPA fallback |
| Backups | `deploy/backup.sh` | `pg_dump` **and** `media/` in one timestamped bundle with `SHA256SUMS` and a manifest, retention by count |
| Restore | `deploy/restore.sh` | verifies checksums, refuses to run while the service is live, restores both halves |
| Post-deploy check | `deploy/smoke.sh` | 17 assertions a non-developer can run after a deploy |
| Production deps | `backend/requirements-prod.txt` | `-r requirements.txt` + gunicorn |
| CI | `.github/workflows/ci.yml` | 5 jobs on every push: SQLite suite + coverage gate, **PostgreSQL suite + migration round-trip**, contract audit, admin build, mobile typecheck + export |

## 3. The architecture it assumes

```
                    ┌──────────────────────────────────────────┐
  phone (Expo)  ───▶│  nginx :443  (TLS, HSTS, CSP, rate limit) │
  browser       ───▶│    /            → admin SPA (static)     │
                    │    /api/v1/…    → 127.0.0.1:8010          │
                    │    /api/v1/chat/ws/… (Upgrade) → same     │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────┐   ┌───────────────────┐
                    │ gunicorn (5 × UvicornWorker) │──▶│ PostgreSQL 16/17  │
                    │ stateless; no local schedule │   └───────────────────┘
                    └───────────────┬──────────────┘
                                    │ writes
                            /var/lib/ssuet-rideshare/media
```

One origin is deliberate: no CORS in the browser, no mixed-content problems for the
mobile app, and the upload cap lives in one place.

## 4. What was actually executed here

### 4.1 The shipped nginx config, with real TLS
Installed exactly as shipped (`/etc/nginx/sites-available/ssuet-rideshare.conf`), with a
local CA so the certificate chain verifies for real:

```
$ sudo nginx -t
nginx: configuration file /etc/nginx/nginx.conf test is successful
$ curl -sI https://rideshare.ssuet.edu.pk/ | grep -iE 'strict-transport|x-frame|content-security'
strict-transport-security: max-age=31536000; includeSubDomains
x-frame-options: DENY
content-security-policy: default-src 'self'; … frame-ancestors 'none'; …
$ curl -s https://rideshare.ssuet.edu.pk/api/v1/health
{"status":"ok","version":"0.1.0","environment":"production"}
$ curl -s -o /dev/null -w '%{http_code} → %{redirect_url}\n' http://rideshare.ssuet.edu.pk/api/v1/health
301 → https://rideshare.ssuet.edu.pk/api/v1/health
```

### 4.2 The shipped smoke test
```
$ SMOKE_EMAIL=admin@example.com SMOKE_PASSWORD=… ./deploy/smoke.sh https://rideshare.ssuet.edu.pk
PASS GET /health (200)              PASS GET /.env (must be refused) (403)
PASS health reports ok              PASS GET /meta through the proxy (200)
PASS GET /health/ready (200)        PASS meta payload parses
PASS HSTS present                   PASS GET /admin/dashboard without a token (401)
PASS TLS certificate verifies       PASS POST /auth/login (200)
PASS security header nosniff        PASS oversize upload is refused (413)
PASS security header x-frame-options
PASS security header content-security-policy
PASS GET / (admin console) (200)    PASS GET /reports (client route → shell) (200)
PASS SPA shell served
17 passed, 0 failed
```
Two of those checks failed on the first run and produced real fixes (§6).

### 4.2a The console itself, served by nginx over TLS
Playwright against `https://rideshare.ssuet.edu.pk` (the certificate chain trusted via the
local CA): `/login` loads the real SPA over HTTPS, signing in reaches **Operations
overview**, `/users` lists **13 members**, **0 console errors** — the CSP above allows the
bundle and blocks everything else. Screenshot:
`screenshots/phase11-production-console.png`.

### 4.3 Beyond the smoke test
| Check | Result |
| --- | --- |
| Upload through the proxy | 201, 75 B `image/png`, stored under `MEDIA_ROOT` |
| Read it back through the proxy | 200, bytes identical, `inline` disposition, buffering off |
| 7 MB upload | **413 at the edge** (`client_max_body_size 6m`) before it reaches Python |
| WebSocket chat over `wss://` | `ready` frame, message echo, persisted and readable over REST — gunicorn workers + `Upgrade` headers + `proxy_read_timeout 3600s` |
| Edge rate limit on `/auth/login` | 14 rapid attempts → **429** (`limit_req_status 429`) |
| Backup | `database.sqlite3` 636 KB + `media.tar.gz` (3 files) + `MANIFEST` + `SHA256SUMS`, all checksums OK |
| Restore rehearsal | media tarball extracted into a scratch dir → `diff -r` against the live `MEDIA_ROOT` identical; restored DB queried (13 users, 3 media rows) |

### 4.4 PostgreSQL parity
```
$ DATABASE_URL=postgresql+psycopg://… alembic upgrade head && alembic check
… 1ecaa4a7e72e → down_revision applied
No new upgrade operations detected.

$ DATABASE_URL=postgresql+psycopg://…ssuet_rideshare python -m scripts.seed
Seed complete.

$ TEST_DATABASE_URL=postgresql+psycopg://…ssuet_test python -m pytest
353 passed in 154.60s
```
**The whole suite passes on PostgreSQL 17**, and a seeded API on Postgres answers
`/health`, `/health/ready`, login, the explore feed, the admin dashboard (6/6 checks).
`tests/conftest.py` now honours `TEST_DATABASE_URL`, which is what CI uses.

## 5. CI

`.github/workflows/ci.yml` — five jobs, no secrets required:

| Job | What it proves |
| --- | --- |
| `backend · sqlite` | `compileall`, full suite, coverage gate **≥ 90 %** (currently 94 %) |
| `backend · postgres + migrations` | full suite against a `postgres:16` service; `alembic upgrade head` → `check` → `downgrade base` → `upgrade head` |
| `API ↔ documentation contract` | `python -m scripts.check_contracts` |
| `admin console` | `npm ci`, `tsc --noEmit`, `npm run build`, uploads `dist/` |
| `mobile app` | `npm ci`, `tsc --noEmit`, `expo export --platform android`, reports bundle size |

Locally rehearsed: `compileall` ✓, suite + coverage gate ✓ (`Required test coverage of
90% reached. Total coverage: 93.99%`), Postgres job ✓, contract audit ✓, admin build ✓,
mobile export ✓. The workflow file parses and every command in it has been run here.

## 6. Defects the rehearsal caught (and fixed)

1. **Security headers silently dropped on the console.** `add_header Cache-Control` inside
   `location = /index.html` and `location /assets/` replaced the *server-level* header set
   — HSTS, CSP and `X-Frame-Options` disappeared exactly on the HTML page that needs them.
   Fixed by using `expires` (which does not reset inheritance) instead of `add_header`.
2. **Rate limiting answered 503.** nginx's default `limit_req_status` is 503, which tells a
   client "the server is broken"; the app and mobile client already understand 429.
   Set `limit_req_status 429`.
3. **`backup.sh` broke on an unquoted space** in the environment file (`ADMIN_NAME=SSUET
   RideShare Administrator`). The scripts no longer `source` the file at all — they parse
   the keys they need with Python, which is safe against shell metacharacters too. The
   example file now quotes spaced values.
4. **Static directory unreadable by the nginx worker** (a sandbox artifact, but a genuine
   deployment trap): `/srv/…` must be `a+rX` for `www-data`. Noted in §7.

## 7. Deployment checklist (the parts a human must do)

1. **DNS** — `rideshare.ssuet.edu.pk` → the VPS IP.
2. **TLS** — `sudo certbot --nginx -d rideshare.ssuet.edu.pk` (the shipped config already
   serves `/.well-known/acme-challenge/` from `/var/www/certbot`).
3. **Service user and paths** — `ssuet` user, `/srv/ssuet-rideshare` (readable by nginx),
   `/var/lib/ssuet-rideshare/media` (writable by `ssuet` only), `/etc/ssuet-rideshare/api.env`
   `root:ssuet 0640`.
4. **Database** — `createdb ssuet_rideshare`, `alembic upgrade head`, then seed or create
   the first administrator, then set `ADMIN_BOOTSTRAP_ENABLED=false`.
5. **Cron** (the API runs stateless, `MAINTENANCE_INTERVAL_MINUTES=0`):
   ```cron
   */15 * * * * cd /srv/ssuet-rideshare/backend && .venv/bin/python -m scripts.expire_stale_rides
   15 3   * * * /srv/ssuet-rideshare/deploy/backup.sh >> /var/log/ssuet-backup.log 2>&1
   30 3   * * * cd /srv/ssuet-rideshare/backend && .venv/bin/python -m scripts.sweep_media
   ```
6. **SMTP + Maps key** (optional): fill `SMTP_*`; without them email is logged and the app
   falls back to area-based maps.
7. **Mobile** — `cd mobile && eas build -p android --profile production`, set
   `EXPO_PUBLIC_API_URL=https://rideshare.ssuet.edu.pk/api/v1` at build time.
8. **Post-deploy** — `./deploy/smoke.sh https://rideshare.ssuet.edu.pk`, then work through
   the 14-point device checklist in doc 12 §4.

## 8. What this phase does not claim

* **No real server was provisioned.** Everything above ran on one Linux host in this
  sandbox; a real VPS needs the same steps plus the DNS/certbot lines in §7.
* **systemd was not executed** (this container has no PID 1 systemd). The unit file is
  syntax-checked and mirrors the exact gunicorn command line that *was* run for real,
  including the worker class, bind address and forwarded-IP trust.
* **No load test at production scale.** Phase 8's numbers (≈100–330 rps per endpoint on
  SQLite, 20 concurrent clients) remain the reference; with Postgres and five workers the
  real ceiling is a measurement for the pilot, not a claim to make now.
* **No WAF, no fail2ban, no monitoring agent.** The edge rate limits and the health
  endpoints are the minimum; an uptime monitor on `/api/v1/health/ready` is the next
  cheap win.
