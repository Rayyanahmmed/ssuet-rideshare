# 7. Phase 3 — Core Ride System (implementation record)

This document records *what* Phase 3 shipped, *why* it is built the way it is, and
*how to verify it*. It complements the contracts in
[`03-api-contracts.md`](03-api-contracts.md) — where the two disagree, the code is
authoritative and this file is the changelog.

---

## 7.1 The one business rule that shapes everything

> **A published ride can have exactly one confirmed passenger.**

That rule is enforced in **three independent layers**, in this order:

| Layer | Mechanism | Prevents |
|---|---|---|
| 1. Row lock | `SELECT … FROM rides WHERE id = :id FOR UPDATE` | Two drivers-side transactions reading the seat as free at the same time |
| 2. In-transaction check | Ride status must be `OPEN` (or `MATCHED` with `seats_remaining > 0`) and the request must still be `PENDING` | Accepting a request on a cancelled / already-matched ride |
| 3. Database | Partial unique index `uq_trips_one_active_per_ride` on `trips(ride_id) WHERE status IN ('CONFIRMED','IN_PROGRESS')` + `CHECK (seats_remaining >= 0)` | Any future code path (script, admin action, data import) that bypasses the service layer |

`RequestService.accept_request` also translates a lost race into a clean API answer
rather than a stack trace: it raises **`SeatUnavailableError` → 409 `RIDE_NOT_AVAILABLE`**
*before* the generic conflict check, because by then the losing request has already
been auto-`REJECTED` by the winner (checking request status first would have returned
the misleading `CONFLICT`).

**Proof:** `backend/tests/test_requests.py::test_concurrent_accepts_yield_single_winner`
runs four threads against one ride and asserts exactly one `ACCEPTED`, three
`RIDE_NOT_AVAILABLE`, one trip row, `seats_remaining = 0`, `status = MATCHED`. A second
test inserts a duplicate active trip directly and asserts `IntegrityError` — i.e. the
DB protects us even if the service is bypassed.

---

## 7.2 Backend surface added

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /vehicles` | member | My vehicles, newest first |
| `POST /vehicles` | member | Register a car/bike → `PENDING` verification |
| `PATCH /vehicles/{id}` | owner | Edit details → returns to `PENDING` |
| `DELETE /vehicles/{id}` | owner | Soft delete; blocked while the vehicle is on an open ride |
| `POST /rides` | verified | Publish a journey |
| `GET /rides` | public (auth-aware) | Explore feed with all filters + cursor |
| `GET /rides/mine` | member | Journeys I published |
| `GET /rides/{id}` | auth-aware | Detail with privacy projection |
| `PATCH /rides/{id}` | driver | Edit note / fare / seats while `OPEN` |
| `POST /rides/{id}/cancel` | driver | Cancel → notifies requester(s) |
| `POST /rides/{id}/requests` | verified | Ask for the seat |
| `GET /rides/{id}/requests` | driver | Requests for one journey |
| `GET /requests/mine` | member | Requests I sent (with ride summary) |
| `GET /requests/inbox` | member | Driver inbox across all my journeys |
| `POST /requests/{id}/accept` | driver | **Atomic seat claim** → returns the created `TripOut` |
| `POST /requests/{id}/reject` | driver | Decline with an optional note |
| `POST /requests/{id}/cancel` | requester | Withdraw a pending request |

### Contract details worth remembering

* **Campus end is not user-editable.** `HOME_TO_UNIVERSITY` forces
  `destination_area = "SSUET, University Road, Karachi"`; `UNIVERSITY_TO_HOME` forces the
  same value as the pickup. A phone-typed "SSUET" in the wrong field is impossible.
* **Seats.** `available_seats` is accepted for future multi-seat support but Phase 3
  always stores `seats_remaining = 1`.
* **Fare matrix.** `FREE` rejects any contribution field (`422`); `SHARE_FUEL` requires a
  `contribution_type`; `NEGOTIABLE` rejects a fixed amount.
* **Privacy projection** (`RideOut` vs `RideDetailOut`): strangers receive
  `pickup_area` / `destination_area` only. `pickup_point`, `destination_point` and
  `driver_phone` are populated only for the driver, the accepted passenger, or an admin.
  The driver inbox returns the requester's trust signals (verification, rating, completed
  trips) but **never** their phone number.
* **Cursor pagination** is `base64("<departure_at ISO>|<ride id>")` ordered by
  `(departure_at ASC, id ASC)`; `next_cursor` is `null` on the last page and an
  unparsable cursor returns `422`.
* **Request eligibility** — verified account (`403 ACCOUNT_NOT_VERIFIED`), not your own
  ride (`422`), not a blocked pair (`403`), no existing pending/duplicate request
  (`409`), ride still open and in the future.

---

## 7.3 Mobile surface added

| Screen / module | File | Notes |
|---|---|---|
| Typed data layer | `src/api/rides.ts` | Every ride/request/vehicle call the app makes; types mirror the Pydantic schemas exactly |
| Ride card | `src/components/RideCard.tsx` | Driver + verification tick + rating, area route, time, vehicle, free/fuel badge, seat count, my-request badge |
| Skeletons | `src/components/Skeleton.tsx` | Animated shimmer block + full card skeleton |
| Area + pin picker | `src/components/LocationPicker.tsx` | Area chips, free-text search, "use my current location" (`expo-location`), interactive map when a key exists |
| Karachi area centroids | `src/lib/areas.ts` | Default pin per area so publishing works with **no** Maps key |
| Explore | `app/(tabs)/explore.tsx` | Direction toggle, area search, fare/vehicle filters, skeletons, retry + empty states, cursor "Load more" |
| Ride detail | `app/ride/[id].tsx` | Route card or map, driver & vehicle trust block, fare disclaimer, request bottom sheet, meeting point + chat hint once accepted |
| Publish wizard | `app/(tabs)/publish.tsx` | 5 steps with per-step validation, review card, "departure ≥ 5 min in future" guard |
| My Rides | `app/(tabs)/my-rides.tsx` | Published (with inline Accept/Reject), Requested, Upcoming, Completed, Cancelled |
| Vehicles | `app/vehicles.tsx` | Register car/bike, see verification status and admin note |
| Home | `app/(tabs)/index.tsx` | Replaced the Phase-2 placeholder with the three nearest real journeys |

### Map fallback decision (§13)

`expo-location@~19.0.8` and `react-native-maps@1.20.1` are installed. The app renders a
map through the server-side tile proxy (OpenStreetMap by default; Geoapify/MapTiler key is set in Admin → Map API, no rebuild)
(`extra.mapsKeyConfigured`). Otherwise every map slot is replaced by an area card or an
explanatory placeholder, and publishing/detail/request keep working end-to-end. That is
why a review build without a key still passes a real device test.

> Dependency note: `react-dom` is pinned to `19.1.0` (matching `react`) in
> `package.json`. `npm install` otherwise fails `ERESOLVE` because a transitive
> `react-dom@19.3.1` demands a newer React than Expo SDK 54 allows.

### UX rules applied on every new screen

* Light theme, navy/white/fresh-green palette, rounded 16–20px cards, soft shadow.
* Loading → skeleton; empty → illustration icon + explanation + **one clear action**;
  error → API message + Retry (never a blank screen).
* Every consequential action asks for confirmation (`Alert`) and every failure surfaces
  the backend's human-readable message (`ApiError.message`) instead of a generic error.
* Accept/Reject invalidate `my-rides`, `driver-inbox`, `my-requests` and `rides` so a
  concurrent loss shows the true state (ride becomes `MATCHED`, other requests rejected).
* No hardcoded ride data anywhere: home, explore, detail, my rides all read the API.

---

## 7.4 How to verify Phase 3 by hand

```bash
# 1. Backend
cd backend && source .venv/bin/activate
python -m pytest                 # 129 passed
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Mobile (second terminal)
cd mobile && npx tsc --noEmit    # 0 errors
npx expo start --android         # or scan the QR from Expo Go / a dev build
```

Seeded accounts (`password: Password123!`): `ali@ssuet.edu.pk`,
`fatima@ssuet.edu.pk`, `ahmed@ssuet.edu.pk`, `drfaheem@ssuet.edu.pk`.

**Scripted happy path**

1. Sign in as **Ali** → Publish a ride (Home → SSUET, Gulshan-e-Iqbal, tomorrow 08:00,
   car, *Free ride*) → journey appears in Explore for other members.
2. Sign in as **Fatima** → Explore → open Ali's journey → *Request to join*.
3. Back as **Ali** → My Rides → Published → the request card shows Fatima's department,
   verification tick and rating → ✅ Accept.
4. Ali's ride becomes `MATCHED` with 0 seats; Fatima's request shows `ACCEPTED` and the
   detail screen reveals the meeting point. A phone-less request inbox, a rejected
   duplicate, and a `409 RIDE_NOT_AVAILABLE` on the second accept are all reproducible
   from the same flow.

---

## 7.5 Explicitly deferred (carried into later phases)

| Item | Phase |
|---|---|
| Trip lifecycle (`/trips/*`: start, complete, cancel, no-show), both-sides confirmation | 4 |
| My Rides → Upcoming/Completed filled by real trips, rating prompt after completion | 4 / 7 |
| Trip chat (WebSocket) linked from the accepted ride card | 5 |
| Push notification delivery for `ACCEPTED` / `REJECTED` (records already persisted) | 5 |
| Admin verification queues (users, vehicles) and published-rides moderation | 6 |
| Blocked-pair messaging inside chat, report/complaint flows | 7 |
