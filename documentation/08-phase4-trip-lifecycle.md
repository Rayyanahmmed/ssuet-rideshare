# 8. Phase 4 — Trip Lifecycle (implementation record)

Phase 3 answered *“can I travel with this person?”*. Phase 4 answers *“what happens
now that we are travelling together?”* — start, finish, cancel, no-show, plus the
two clock-driven jobs that keep the table clean without anyone pressing anything.

---

## 8.1 The state machine (and why it is this shape)

```
                    ┌──────────── start (driver) ─────────────┐
CONFIRMED ──────────┤                                         ▼
   │                │                                   IN_PROGRESS
   │                │                                         │
   │  cancel (both) │                       complete (driver)  │  complete (passenger)
   │  no-show(drv)  │                             │           │            │
   ▼                ▼                             ▼           ▼            ▼
CANCELLED ◀─────────┘                    both sides confirmed ──▶ COMPLETED
NO_SHOW ──── driver may still close the ride ─────▶ (ride only)
```

| Rule | Reason |
|---|---|
| **Only the driver can start** | The person with the keys decides when the journey began; the passenger cannot declare a trip running. |
| **Start window: −6 h / +12 h around departure** | Early for labs, traffic and exams; late enough to survive a late start; beyond +12 h the maintenance job expires it instead of leaving a zombie trip. |
| **Completion needs both sides** | Each side sets its own flag. A driver cannot inflate `completed_trips_count`, and a passenger cannot close a journey that never happened. The payload exposes `awaiting_my_confirmation` so the app can prompt the second person. |
| **Passenger cancels → ride reopens** | The seat is restored (`status OPEN`, `seats_remaining = available_seats`, `matched_at` cleared) while the departure is still in the future, so someone else can travel with the same driver. Proven by a test that accepts a *different* passenger on the same ride afterwards. |
| **Driver cancels → ride dies** | Nobody is driving any more: the ride becomes `CANCELLED` and everyone still waiting is declined with a note. |
| **Passenger cannot cancel after start** | Once the journey is running this is a safety matter, not a booking one — the copy points them to the driver and the report flow (Phase 7). |
| **No-show is separate from cancel** | `NO_SHOW` keeps the two situations distinguishable for the admin dashboard and reports. Before departure the seat frees up again; after departure the driver travelled alone and the ride closes as `COMPLETED`. |
| **Illegal transitions fail closed** | Every mutation validates against `TRIP_STATUS_TRANSITIONS` / `RIDE_STATUS_TRANSITIONS` and returns `409 CONFLICT` with a human message. |

---

## 8.2 Backend surface added

| Method & path | Who | Behaviour |
|---|---|---|
| `GET /trips/mine?role=&status=&upcoming=&limit=` | participant | My trips; `upcoming=true` → live ones soonest-first, `upcoming=false` → history newest-first |
| `GET /trips/{id}` | participants + admin | Full trip: meeting point, both phone numbers, per-side completion flags, next actions |
| `POST /trips/{id}/start` | driver | `CONFIRMED → IN_PROGRESS`, ride `IN_PROGRESS`, notifies the passenger (`TRIP_STARTED`) |
| `POST /trips/{id}/complete` | both | Records my confirmation; finalises when both are set (`TRIP_COMPLETED` to both, counters incremented, ride `COMPLETED`) |
| `POST /trips/{id}/cancel` | both | Reason recorded + `TRIP_CANCELLED` notification; ride reopened or cancelled depending on the actor |
| `POST /trips/{id}/no-show` | driver | `NO_SHOW`, passenger notified (`TRIP_NO_SHOW`), seat or ride freed |

Every response is a `TripOut` carrying viewer-specific flags — `my_role`,
`can_start`, `can_complete`, `can_cancel`, `can_mark_no_show`,
`awaiting_my_confirmation`, `can_review` — so the app asks the backend *“what can I
do now?”* instead of re-implementing the state machine in TypeScript.

### New notification templates

`TRIP_STARTED`, `TRIP_AWAITING_CONFIRMATION`, `TRIP_NO_SHOW`, and an improved
`TRIP_COMPLETED` (now names the counterpart so the future rating prompt makes
sense). All are persisted rows today; Phase 5 fans them out to Expo push without
touching the call sites.

---

## 8.3 Housekeeping — nothing waits for a button (§10)

`app/services/maintenance_service.py` implements the two clock jobs:

| Job | Trigger | Effect |
|---|---|---|
| `expire_stale_rides` | `OPEN`/`MATCHED` ride older than departure + grace (default 60 min, `RIDE_AUTO_EXPIRE_GRACE_MINUTES`) | Ride → `EXPIRED`; pending requests → `CANCELLED` with a note; a trip that was never started → `CANCELLED` (`abandoned_trips`); everyone involved is notified |
| `auto_complete_stale_trips` | `IN_PROGRESS` trip started > 24 h ago where **one** side already confirmed | Trip → `COMPLETED` with both flags set, counters incremented, ride `COMPLETED` — so one silent member cannot freeze the other's history |

Three ways to run them (pick per environment):

```bash
# 1. Built in: the API process runs them every MAINTENANCE_INTERVAL_MINUTES (default 15, 0 = off)
#    — a background asyncio task in app.main, executed in a worker thread.

# 2. On demand / from cron (recommended for multi-worker production)
cd backend && python -m scripts.expire_stale_rides
python -m scripts.expire_stale_rides --grace 15 --dry-run

# 3. From code/tests
from app.services.maintenance_service import run_all
run_all(db, grace_minutes=60)
```

---

## 8.4 Mobile surface added

| Screen / module | File | Notes |
|---|---|---|
| Typed trip layer | `src/api/trips.ts` | `listTrips`, `getTrip`, `startTrip`, `completeTrip`, `cancelTrip`, `markNoShow` |
| Trip card | `src/components/TripCard.tsx` | Counterpart, route, time, status badge, and a one-line "what next" hint (ready to start / waiting for you) |
| Trip detail | `app/trip/[id].tsx` | Status, journey snapshot, counterpart with **call button**, meeting point, per-side completion checklist, reason sheet for cancel/no-show, sticky primary action |
| My Rides | `app/(tabs)/my-rides.tsx` | **Upcoming / Completed / Cancelled now read real trips**; Published (accept/reject) and Requested stay as in Phase 3 |
| Ride detail | `app/ride/[id].tsx` | Accepted passengers get an **Open trip** button (uses the new `my_trip_id` field on the ride payload) |

UX details worth keeping:

* The sticky footer is a single decision: `Start journey` → `Confirm trip finished` →
  "you have confirmed" — never a wall of buttons.
* Cancel is destructive and asks for an optional reason (shown to the other member
  and to admins); no-show is behind a confirmation dialog because it affects
  someone's record.
* Trip chat is explicitly labelled "arrives in Phase 5" with a working call button
  in the meantime — no dead buttons (§26.9).

---

## 8.5 Verification

```bash
cd backend && python -m pytest          # 164 passed (129 + 35 trip tests)
cd mobile  && npx tsc --noEmit          # 0 errors
              npx expo export --platform android   # bundles clean (≈3.9 MB HBC)
cd backend && python -m scripts.expire_stale_rides --dry-run
```

`tests/test_trips.py` (35 tests) covers: accept → trip visible to both sides, role
and `upcoming` filters, third-member 403, unauthenticated 401, unknown trip 404,
driver-only start, double start, start-too-early, both-sides completion, counter
increments, completion-before-start, double confirmation, terminal states,
passenger cancel reopening the seat (**and a different passenger being accepted
afterwards**), driver cancel killing the ride, passenger cancel after start,
outsider cancel, no-show before/after departure, no-show too early, driver closing
after a no-show, contact-sharing privacy, and the four maintenance scenarios.

**Live API proof (dev server, real DB):**

```
start                      200 IN_PROGRESS  can_complete=True
passenger confirms first   200 IN_PROGRESS  awaiting driver confirmation
driver view                awaiting_my_confirmation=True
driver confirms            200 COMPLETED    can_review=True
completed_trips_count      ali=1  fatima=1
cancel after completion    409 CONFLICT
third member reads trip    403 FORBIDDEN
```

---

## 8.6 Deferred to later phases

| Item | Phase |
|---|---|
| Trip chat screen wired to `conversation_id` (WebSocket) | 5 |
| Push delivery for `TRIP_STARTED` / `TRIP_COMPLETED` | 5 |
| Ratings & reviews after completion (`can_review` already returned) | 7 |
| Admin trip monitoring, force-cancel, no-show reports | 6 |
| Reminder notifications ("your journey starts in 30 minutes") | 5 |
