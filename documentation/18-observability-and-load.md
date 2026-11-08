# 18 · Phase 12 — observability & load validation

**Status:** complete. The service now tells you what is wrong instead of waiting to be
asked, and its capacity on real infrastructure has been measured rather than assumed.

```
backend$  python -m pytest tests/test_observability.py      # 12 passed (365 total, 94 %)
backend$  python -m scripts.load_check run --base-url …      # doc 18 §4, testing/load-postgres.txt
deploy$   ./monitor.sh                                       # 5 checks, exit 0 / 1 / 2
```

---

## 1. The gap this closes

Phase 11 made the app deployable. That exposed the next problem: once it is running
somewhere else, "is it healthy?" was still answered by SSH-ing in and guessing. There was
a request-id middleware and a `/health` probe, but nothing that said *the schema is
behind head*, *the disk is filling*, or *Explore p95 just tripled*. And every performance
claim came from Phase 8, measured on SQLite with a single worker.

## 2. What shipped

| Layer | Addition |
| --- | --- |
| Request correlation | every response carries `X-Request-ID` (yours, if you sent one), `X-Process-Time-Ms` and `Server-Timing`; slow requests log `SLOW METHOD path → status in N ms (request_id=…)` at a configurable `SLOW_REQUEST_MS` (default 500) |
| Live panel | `GET /admin/health` (admin only): database latency + dialect + **schema revision vs head** + pool, the review queues, media storage and free disk, last housekeeping run, and a `warnings[]` list |
| Deep probe | `GET /health/ready` stays as the cheap load-balancer probe; `/health` never touches the database, so it answers while the DB is down |
| Monitoring | `deploy/monitor.sh` — liveness (with latency budget), readiness, certificate expiry, disk free, backup freshness; exit 0 / 1 (warning) / 2 (failure); optional `ALERT_WEBHOOK` POST |
| Scheduling | `deploy/ssuet-monitor.service` + `.timer` (every 15 min, `SuccessExitStatus=0 1`) |
| Load tool | `scripts/load_check.py` can now measure the real stack (`--insecure` for a rehearsal certificate) — see §4 |

## 3. The panel, live

```json
{
  "status": "ok", "version": "0.1.0", "environment": "production",
  "process": {"pid": 649554, "uptime_seconds": 6.3},
  "database": {"ok": true, "latency_ms": 0.15, "slow": false, "dialect": "sqlite",
               "schema_revision": "1ecaa4a7e72e", "schema_head": "1ecaa4a7e72e",
               "pool": {"size": 5, "checked_out": 1, "overflow": 0}},
  "queues": {"pending_verification_requests": 2, "members_awaiting_verification": 2,
             "pending_vehicles": 1, "open_reports": 1, "open_rides": 7,
             "matching_rides": 1, "trips_in_progress": 0, "members": 13},
  "media": {"root": "…/media", "files": 3, "bytes": 5085, "orphans": 0,
            "disk_free_bytes": 18391781376, "disk_total_bytes": 26181988352},
  "housekeeping": {"interval_minutes": 0, "last_run_at": null, "last_result": null,
                   "slow_request_threshold_ms": 500},
  "warnings": []
}
```

The two fields that catch real incidents before users do:

* `schema_revision` vs `schema_head` — a deployment that forgot `alembic upgrade head`
  says so in plain words (`"…run alembic upgrade head and stamp it"`). Covered by a test.
* `status: "degraded"` + `warnings[]` — a database round-trip above 100 ms, or a media
  volume below 10 % free, flips the panel. Also covered by a test.

## 4. Capacity, measured on the production stack

Full tables: `documentation/testing/load-postgres.txt`. The short version — nginx + 5
gunicorn workers + PostgreSQL 17 on a 2-vCPU host:

| Question | Answer |
| --- | --- |
| What does a student feel? | **11.6–13 ms** for Explore (20 rides, 18.2 KB) |
| Where does the time go? | 2.5 ms SQL (4 statements), ~10 ms Python/serialisation — **not** the database |
| How does it scale with concurrency? | 13 → 31 → 62 → 98 → 116 ms p50 at 1/5/10/20/40 concurrent |
| Where is the plateau? | **~145–150 rps** for Explore, 0 errors across 1,400 requests |
| What does the proxy cost? | **3–7 ms** (TLS + one hop), measured nginx vs direct |
| Is 5 workers right? | On 2 vCPU, no: 2 workers → 97 rps, 5 → 105–145 rps; past the core count you buy queueing, not throughput |
| Versus Phase 8 (SQLite, 1 worker) | 101.9 → ~145 rps, p50 178.6 → ~100 ms, p95 311 → ~230 ms |

~145 rps ≈ **8,700 requests/minute** on the cheapest VPS the university would buy. The
first attempt at measuring *through* nginx also produced a useful negative result: a
single IP pushing 400+ rps gets **429** from the edge limiter — the throttle works, which
is why the throughput numbers are taken against the app directly and the proxy is
measured separately.

## 5. Monitoring, demonstrated in both directions

Healthy (production stack, TLS, certificate, backups present):
```
$ ./deploy/monitor.sh
OK    liveness 200 in 29 ms
OK    readiness 200 (database reachable)
OK    certificate valid for 29 day(s)
OK    media volume 71% free
OK    newest backup is 1 h old
SSUET RideShare monitor: 0 failure(s), 0 warning(s)   → exit 0
```

With the API stopped (the way a deploy gone wrong looks):
```
FAIL  liveness returned 502
FAIL  readiness returned 502
…
SSUET RideShare monitor: 2 failure(s), 0 warning(s)   → exit 2
```
and with `ALERT_WEBHOOK` set, the summary was POSTed to a local sink and received:
`{"text":"SSUET RideShare monitor: 2 failure(s)…FAIL liveness returned 502;…"}`.

## 6. Request correlation in practice

```bash
$ curl -sI https://rideshare.ssuet.edu.pk/api/v1/health | grep -iE 'x-request-id|process-time|server-timing'
x-request-id: 4f1c9a7b2e10
x-process-time-ms: 3.4
server-timing: app;dur=3.4
```
nginx passes `X-Request-ID` through untouched, so a request id in a student's screenshot
matches the gunicorn log line, the access log entry, and (if you add one) the error
tracker.

## 7. The bug the PostgreSQL run caught

The panel passed twelve tests on SQLite and returned **500 on PostgreSQL** for two of
them. Reading the migration revision with a bare `SELECT version_num FROM
alembic_version` throws when the table does not exist — and on PostgreSQL a failed
statement **aborts the whole transaction**, so every later query in the same request
died with `current transaction is aborted, commands ignored until end of transaction
block`. On SQLite the same mistake was invisible, because there the session keeps
working after a failed statement.

Fixed by checking table existence with the inspector and wrapping the read in a
savepoint, so a database created by `AUTO_CREATE_TABLES` (no `alembic_version` row)
degrades to `schema_revision: null` plus a warning instead of a crash. This is exactly
what the CI `postgres` job exists for: a dialect difference that no amount of SQLite
testing would have surfaced.

## 8. What this still does not do

* **No metrics scraping endpoint.** The panel is JSON for humans; Prometheus would want
  `/metrics` and a client library. If the pilot is monitored seriously, that is the next
  step, not a rewrite.
* **No log shipping.** Logs go to journald/nginx files; `deploy/monitor.sh` is poll-based.
  A hosted log drain is a 15-minute job once there is a host to point it at.
* **Load numbers are from a shared 2-vCPU sandbox** and vary ±20 % between runs. They
  answer "will a campus pilot work?" (yes, with a wide margin) — not "what is the exact
  ceiling of this VPS".
* **`/admin/health` is not in the console UI.** It is one authenticated GET; the runbook
  (doc 13 §6a) shows the curl. A panel in the dashboard is cosmetic work for later.
* **No APM/tracing.** Request ids + timings are the 80 % of it; distributed tracing has
  nothing to trace in a single-service deployment.
