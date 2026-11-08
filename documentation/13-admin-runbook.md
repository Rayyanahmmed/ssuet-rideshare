# Admin Runbook — SSUET RideShare

Whoever runs the platform day to day (the ride-share office) needs four things: sign
in, clear the queues, handle an incident, and keep the service healthy. This is that
script — no code reading required.

> **Looking for the printed handover?** [`22-operations-handbook.md`](22-operations-handbook.md)
> (and its [PDF](22-operations-handbook.pdf)) is the distilled, signable version of this
> document plus docs 17–21 — day one, the routine, and the incident playbooks.

---

## 1. Signing in

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
cd admin-dashboard && npm run dev        # http://localhost:5173
```

Use the administrator account created from the backend environment:

| Variable | Meaning |
| --- | --- |
| `ADMIN_NAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` | the first admin, created **once** on startup |
| `python -m scripts.set_admin_password` | create an admin or **reset an existing admin password** |

**"Incorrect email or password" on the console sign-in page?** The bootstrap creates the admin
only when it does not exist — after that, `ADMIN_PASSWORD` in `backend/.env` changes nothing
(the log says `Admin bootstrap skipped: account … already exists (password untouched)`).
Reset it instead:

```bash
cd backend
.venv/bin/python -m scripts.set_admin_password --list
.venv/bin/python -m scripts.set_admin_password --email admin@example.com --password 'Admin@SSUET2026'
```

Windows: `.venv\Scripts\python.exe -m scripts.set_admin_password --email admin@example.com --password "Admin@SSUET2026"`.
The password must be 8-64 characters and not a common one (the same policy as registration).

| `ADMIN_BOOTSTRAP_ENABLED` | set to `false` after the first successful start |

Rules that are worth stating out loud:

* Restarting the API **never** resets an existing admin password.
* Administrators cannot be suspended, rejected or demoted from the console.
* Sign-out clears the session token immediately; a token issued before an account
  was suspended stops working on the next request, not on the next login.

---

## 2. The daily queues

| Queue | Where | Target |
| --- | --- | --- |
| Verification requests | **Verification Requests** | same working day |
| Vehicles awaiting review | **Vehicle Verification** (filter *Pending*) | within 24 h |
| Open complaints | **Reports & Complaints → Complaints** | first response 24 h, resolution 72 h |
| Flagged reviews | **Reports & Complaints → Reviews & ratings** | as reported |
| Suspended accounts | **Suspended Accounts** | review monthly |

Practical notes:

* **Verification** — university-domain sign-ups are auto-verified; only external
  addresses appear here. Approve, or reject with a reason the member can read.
  Approving unlocks publishing and requesting immediately. Since Phase 9 most
  requests arrive with an uploaded card photo: click **View upload** and the image
  opens in a tab (the console fetches it with your admin token, so the link is not
  shareable and cannot be forwarded to anyone outside SSUET). Rows created before
  Phase 9, or by a member who pasted a link, show **Open link** instead.
* **Vehicles** — check the registration number format and the model against the
  photo. A rejection note is shown to the owner, so write it for them, not for us.
  Rejected vehicles can never publish again until re-approved.
* **Complaints** — moving a report to *Under review* needs no note; resolving or
  dismissing **requires** one. The reporter receives it verbatim.
* **Reviews** — hide only what breaks the community rules (abuse, personal data,
  defamation). Hiding recomputes the subject's average instantly; restoring puts it
  back. Both decisions are audited.

---

## 3. Handling an incident

### 3.1 Someone reports harassment or dangerous driving

1. `Users` → search the member → **View** opens the dossier (trips as driver and
   passenger, reports filed and against, vehicles, approval history).
2. `Reports & Complaints` → open the report → set **Under review** and write what
   you are checking.
3. If the complaint is credible and immediate: **Suspend account** with a reason.
   This signs them out on their next request **and cancels their open rides**, so no
   passenger is left waiting — tell the affected passengers if there are any.
4. Resolve the report with the outcome. The reporter sees it in the app.
5. Record the follow-up in the suspension reason so the next admin knows why.

### 3.2 A member needs to be reinstated

`Suspended Accounts` → **Reactivate**. Access is restored immediately and the member
is notified. If the suspension was part of an investigation, do not reactivate until
the report is closed.

### 3.3 A journey must be cancelled from above

`Published Rides` → filter by driver or date → **Cancel ride** with a reason. The
matched passenger is notified and the trip closes as `CANCELLED`; the driver keeps
their account unless you also suspend them.

### 3.4 Two accounts look like the same person

Use the dossier: same phone, same university ID, same vehicle registration or
mirrored reviews are the signals. Suspend the duplicate with the reason "duplicate
account", then ask the member to appeal from their official email.

---

## 4. Reading the numbers

**Dashboard** shows the counters that matter for a weekly report: members, verified
share, pending queues, published rides, active/completed trips, open reports, today's
activity, plus 14 days of sign-ups vs rides.

**Analytics** adds: completion rate, cancellation rate, average rating, fuel-sharing
mix, car/bike mix, travel direction, busiest pickup areas and destinations, and the
full administrative action log (every verification, rejection, suspension,
cancellation, report decision and review moderation).

A healthy week looks like: completion rate above ~80%, no open queues older than the
targets above, and a rating average that moves slowly. A sudden cancellation spike
usually means one driver misusing the platform — check the *Published Rides* filter by
driver before assuming a system problem.

---

## 5. Service health

| Check | How |
| --- | --- |
| API alive | `GET /api/v1/health`, `GET /api/v1/health/ready` |
| Feature flags in effect | **Settings** (read-only — values come from the server environment) |
| Housekeeping running | `Settings` shows the sweep interval; logs contain `Maintenance scheduler active` |
| Stale rides / abandoned trips | `python -m scripts.expire_stale_rides --dry-run` reports without changing anything |
| Push delivery | `Settings` → Expo push enabled? If not, in-app notifications still work |

The API logs one line per maintenance sweep and one per failed push; secret material
is redacted by a log filter, so logs are safe to share when asking for help.

---

## 6. Configuration that changes behaviour

Everything below lives in `backend/.env` (restart required):

| Setting | Effect |
| --- | --- |
| `REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH` | `false` (default): a *pending* vehicle may publish, a rejected one never. `true`: only verified vehicles may publish — stricter, slower onboarding |
| `MAX_CONFIRMED_PASSENGERS` | seats per journey (product rule: 1) |
| `RIDE_AUTO_EXPIRE_GRACE_MINUTES` | how long after departure an unclaimed ride stays visible before the sweep expires it |
| `MAINTENANCE_INTERVAL_MINUTES` | how often the sweep runs (default 15) |
| `RATE_LIMIT_ENABLED` | per-IP limits on auth, reviews and reports |
| `EXPO_ACCESS_TOKEN` | Expo push credentials (optional) |
| `SMTP_*` / `EMAIL_DELIVERY` | real email vs logging links to the console |
| `MEDIA_ROOT` | where uploaded verification documents are written — must be writable and **backed up with the database** |
| `MAX_UPLOAD_BYTES` | per-file cap for uploads (default 5 MB; allowed 64 KB – 25 MB) |
| `MEDIA_ORPHAN_RETENTION_DAYS` | how long an unreferenced upload survives before the sweep deletes it (default 7) |

`/admin/settings` in the console shows the effective values **as booleans**, never the
secrets themselves.

---

## 6a. Is the service healthy right now?

Three commands, in order of what they cost you:

```bash
curl -s https://rideshare.ssuet.edu.pk/api/v1/health/ready   # database + migrations
sudo systemctl status ssuet-api                               # process alive, restarts?
sudo tail -50 /var/log/nginx/ssuet-error.log                  # proxy-level failures
```

One call tells you more than any of those, if you have an admin token:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     https://rideshare.ssuet.edu.pk/api/v1/admin/health | python -m json.tool
```

It reports database latency and whether the schema is at head, the queue sizes, free
disk, and a `warnings[]` list — the panel flags a stale schema, a slow database or a
filling volume for you (doc 18 §3).

**Profile photos are normalised on upload** (doc 20): stored as 512 px WebP with no
EXIF, so a photo that looks sideways or blurry in the console was sent that way. If
`MEDIA_ROOT` fills up, avatars are ~15 KB each — the growth is in documents, which are
stored at full size on purpose.

**A member's photo looks wrong or inappropriate.** Photos are visible to every signed-in
member, so an administrator sees exactly what the community sees: the avatar column in
*Users* and the picture in the member's dossier. When a member reports one it arrives in
*Reports & complaints* with a **Photo** chip and the reason; the handling dialog shows the
reported picture itself and offers **"Also remove the photo"** with the decision. The
reported file is kept as evidence even after removal, so the decision stays auditable
(doc 21). Removing a photo never suspends the account — that stays a separate action.

For the full picture after a deploy or an incident,
`./deploy/smoke.sh https://rideshare.ssuet.edu.pk` runs the same 17 checks the release
process uses and prints one line per check (doc 17 §4.2). For unattended monitoring,
`./deploy/monitor.sh` runs every 15 minutes from `ssuet-monitor.timer`: it checks
liveness with a latency budget, readiness, certificate expiry, disk free and backup age,
exits 2 on failure, and POSTs to `ALERT_WEBHOOK` if you set one (doc 18 §5). Deployment, backups and the
cron entries live in doc 17 §7.

---

## 7. Escalation and handover

* **Contract:** `documentation/03-api-contracts.md` — every endpoint, guard and error
  code. If a screen and this document disagree, the document is right and the screen
  has a bug.
* **Database:** `documentation/02-database-design.md` — ER diagram, status machines,
  constraints. Alembic owns migrations (`alembic upgrade head`).
* **Testing:** `documentation/12-phase8-testing-and-release.md` — how to prove a change
  did not break a journey.
* **Risks:** `documentation/06-risks-and-external-setup.md` — external keys, threats
  and their mitigations.

Before handing over: rotate `ADMIN_PASSWORD`, set `ADMIN_BOOTSTRAP_ENABLED=false`,
confirm `ENVIRONMENT=production`, and make sure `JWT_SECRET_KEY` is a long random
value — the app refuses to boot in production without one.

---

## 8. Uploaded documents: storage, backups, retention

Verification photos live on disk, not in the database (doc 15). What that means for
whoever runs the service:

| Concern | What to do |
| --- | --- |
| **Backups** | Dump the database **and** copy `MEDIA_ROOT`. A database-only restore leaves verification rows pointing at files that no longer exist; the queue would show a broken viewer. |
| **Disk** | Budget ~200–400 KB per verified member (the app downscales to quality 0.7). 5 MB is the hard per-file cap and 10 uploads/minute per IP is the rate limit, so growth is bounded. Watch the volume in whatever monitors the host. |
| **Privacy** | Documents are personal data. Do not copy `MEDIA_ROOT` to a laptop for debugging, do not attach files to tickets, and delete them when a member withdraws an upload. Access is audited only insofar as the admin action log records approvals. |
| **Retention** | Abandoned uploads (never referenced by a verification or a vehicle) are deleted automatically after `MEDIA_ORPHAN_RETENTION_DAYS` (7). Documents that *are* referenced stay until someone withdraws them — a reasonable policy is to delete the card photo once the member is verified and it has been checked (`DELETE /api/v1/media/{id}`); the verification row keeps its audit trail with `document_asset_id` set to null. |
| **Vehicle proof** | The **Vehicle Verification** table has a **Proof** column: *Vehicle photo* / *Registration book* open the uploaded file. Use it before approving — a registration number that does not match the book is the commonest problem. |
| **Sweep** | Runs inside the 15-minute housekeeping loop. If the API is deployed stateless, schedule `python -m scripts.sweep_media` from cron instead (`30 3 * * *`) and check it with `--dry-run` first. |
| **Storage numbers** | `GET /api/v1/admin/media` (or `python -m scripts.sweep_media --stats`) gives `files`, `bytes`, `orphans`, `oldest`. A rising `orphans` count between sweeps means members are abandoning the verification/vehicle forms — worth a look at the screens, not at the disk. |
| **Lost file** | If `GET /media/{id}` returns 404 for a row that exists, the file was removed from disk. Ask the member to re-upload (they can submit again after a rejection) rather than approving blind. |
