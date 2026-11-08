# Phase 8 — Testing, Release & Handover

The last phase is about proving the platform works as a *system* and making it
installable and maintainable: end-to-end journey tests, a coverage report, a load
sanity check, the Android release configuration, and the two documents a successor
actually needs — how to test, and how to run the thing.

**Status:** complete. `pytest` → **314 passing**, coverage **94%**, load sanity
recorded, mobile `expo export` **4.18 MB**, versions bumped to **1.0.0**.

---

## 1. Test strategy

Four layers, each with a different job:

| Layer | File(s) | What it protects |
| --- | --- | --- |
| System / config | `test_system.py`, `test_db_constraints.py` | app boots, health/ready, error envelope, and the *database-level* business rules (one live trip per ride, one pending request per pair, review uniqueness, FK/rating constraints) |
| Feature suites | `test_auth.py`, `test_vehicles.py`, `test_rides.py`, `test_requests.py`, `test_trips.py`, `test_chat.py`, `test_notifications.py`, `test_admin.py`, `test_reviews.py`, `test_reports.py` | the documented behaviour of each module |
| Security & privacy | `test_security.py` | no phone/email/home-coordinate leaks before a match; every id-taking endpoint refuses strangers; suspended tokens die; malformed ids never 500 |
| **Journeys** | `test_journeys.py` | complete user stories across phases — the integration glue |

```
backend$ python -m pytest                      # 314 passed
backend$ python -m pytest tests/test_journeys.py -v
backend$ python -m pytest --cov=app --cov-report=term-missing   # 94%
mobile$  npx tsc --noEmit && npx expo export --platform android
admin-dashboard$ npx tsc --noEmit && npm run build
```

### 1.1 The journey suite (10 stories)

| Test | Story |
| --- | --- |
| `test_journey_publish_discover_match_chat_complete_review` | register → vehicle → publish → discover in Explore → request → accept → chat → start → both-side completion → rate both ways → dashboard agrees |
| `test_journey_passenger_cancels_and_the_seat_returns` | a cancelled seat is immediately usable by another member |
| `test_journey_driver_cancel_notifies_the_matched_passenger` | ride cancellation cascades to the trip and the notification |
| `test_journey_no_show_frees_the_seat_and_blocks_reviews` | driver records a no-show; a no-show trip can never be rated |
| `test_journey_unverified_member_is_gated_until_an_admin_approves` | external email → ID submission → admin approval → publish unlocked |
| `test_journey_rejected_vehicle_can_never_be_used` | rejected vehicle blocks publication (default policy) |
| `test_journey_strict_policy_can_require_a_verified_vehicle` | `REQUIRE_VERIFIED_VEHICLE_FOR_PUBLISH=true` path |
| `test_journey_stale_ride_expires_and_disappears_from_explore` | housekeeping job expires an aged journey and Explore stops showing it |
| `test_journey_safety_report_leads_to_suspension` | report + block → admin suspension → ride cancelled → report resolved → audit trail |
| `test_journey_unread_counts_track_the_whole_story` | unread counters move exactly once per event and return to zero on read-all |

Every assertion in that table failed at least once while the suite was being
written — the vehicle-policy one exposed that the console copy claimed vehicles
must be *verified* while the shipped default only blocks *rejected* ones. The
policy is now documented and both branches are tested.

## 2. Coverage

`documentation/testing/coverage.txt` — **94% overall** across 4,187 statements.

```
TOTAL                                   4187    263    94%
314 passed
```

Lowest-coverage modules are the ones whose code cannot run in a sandbox:
`email_service.py` (51% — SMTP delivery paths), `push_service.py` (85% — Expo
network failures), `chat_hub.py` (84% — socket disconnect races). Everything that
carries business rules (rides, requests, trips, reviews, reports, admin) is 88–100%.

## 3. Load sanity

`scripts/load_check.py` seeds a throwaway database and measures the read paths the
app hits constantly. Full output: `documentation/testing/load-sanity.txt`.

```
400 requests per endpoint, concurrency 20, SQLite, 1 uvicorn worker, 400 live rides

endpoint                       rps      p50      p95      p99      max  errors
explore (default)            101.9    178.6    311.1    414.2    427.9       0
explore (filtered)            91.1    209.1    329.3    412.2    492.4       0
explore (nearby bbox)         93.1    199.0    338.7    431.9    517.8       0
ride detail                  211.1     90.3    126.9    149.0    173.5       0
my trips                     332.1     58.3     75.4     96.6     98.9       0
notifications                281.9     68.6     89.7    110.0    116.6       0
```

Zero failures across 2,800 requests, no pool exhaustion. Reproduce with:

```bash
cd backend
export DATABASE_URL="sqlite+pysqlite:///./load_test.db" AUTO_CREATE_TABLES=true
python -m scripts.load_check seed --drivers 40 --rides-per-driver 10
python -m uvicorn app.main:app --port 8010 &
python -m scripts.load_check run --base-url http://127.0.0.1:8010/api/v1
```

## 4. Android release

### 4.1 Versions

| Item | Value |
| --- | --- |
| `expo.version` | **1.0.0** |
| `android.versionCode` | 1 |
| `android.package` | `com.ssuet.rideshare` |
| scheme | `ssuetrideshare` (deep links: `/trip/{id}`, `/chat/{id}`) |

`versionCode` is incremented automatically for `production` builds
(`eas.json → build.production.autoIncrement`).

### 4.2 Assets (already in `mobile/assets/`)

| File | Size | Used by |
| --- | --- | --- |
| `icon.png` | 1024×1024 | app icon |
| `adaptive-icon.png` | 1024×1024 | Android adaptive icon (navy background) |
| `splash.png` | 1242×2436 | splash (navy `#0B1F3A`, monogram + wordmark) |
| `favicon.png` | 512×512 | web preview |

### 4.3 Build profiles (`mobile/eas.json`)

| Profile | Output | Use |
| --- | --- | --- |
| `development` | APK + dev client | day-to-day work with a custom dev client |
| `preview` | **installable APK** (`:app:assembleRelease`) | FYP demo / supervisor / physical-device testing |
| `production` | AAB | Play Store upload, auto-incrementing version |

```bash
cd mobile
npm install -g eas-cli          # once
eas login                       # Expo account
eas init                        # writes extra.eas.projectId (or set EAS_PROJECT_ID)

eas build -p android --profile preview      # → download URL for the APK
eas build -p android --profile production   # → AAB for the Play Console
```

### 4.4 Environment for a device build

`.env` in `mobile/` (git-ignored; `.env.example` lists the keys):

```env
EXPO_PUBLIC_API_URL=http://192.168.1.5:8000/api/v1   # LAN IP of the API host
# maps: configured in Admin → Map API (no mobile env var needed)
EAS_PROJECT_ID=                                       # from `eas init`
```

### 4.5 Physical-device checklist (run before the demo)

This is the pass the roadmap requires; each line is a thing that has broken, or
could break, on a real phone but not in a simulator.

1. **Install** the `preview` APK fresh (uninstall the old build first) — icon,
   name and splash render, no white flash.
2. **Sign up** with a `@ssuet.edu.pk` address → auto-verified, lands on Home.
3. **Sign up** with a Gmail address → blocked from publishing until an admin
   approves the submitted ID.
4. **Publish** a ride: 5 steps, map pin (or area fallback when no Maps key),
   departure time, FREE and SHARE_FUEL paths.
5. **Explore** from a second device: filters (direction, area), pull-to-refresh,
   and confirm no phone number is visible on the card.
6. **Request** the seat, then **accept** on the driver device → both see the trip,
   meeting point and each other's phone.
7. **Chat**: send from both sides, verify typing indicator, delivery order, and
   that killing the network mid-send shows the retry path.
8. **Notifications**: request permission, receive an in-app row and a system push
   when the request is accepted; tapping it deep-links into the trip.
9. **Start** the journey on the driver device only (passenger has no button),
   **complete** from both sides, watch the trip and ride become `COMPLETED`.
10. **Rate** the trip (1–5 + comment); confirm the rating appears on the other
    profile and the "rate your trip" prompt disappears.
11. **Report** a problem + **block** the member; confirm their rides vanish from
    Explore and chat is refused.
12. **Admin console** on a laptop: approve the verification, see the report,
    resolve it, hide the review — then confirm the phone shows the outcome.
13. **Offline**: airplane mode → screens show their error state with a retry, never
    a blank screen or a spinner that never stops.
14. **Rotation / small screen**: 5-inch device, no clipped buttons, keyboard does
    not hide the submit button.

## 5. Release ritual

```bash
# 1. Backend
cd backend
python -m pytest                                  # must be green (314)
python -m scripts.check_contracts                 # API ↔ docs must exit 0 (89 / 87)
alembic upgrade head                              # PostgreSQL
python -m scripts.seed                            # dev only

# 2. Admin console
cd ../admin-dashboard
npm ci && npm run build                           # dist/ is the artefact

# 3. Mobile
cd ../mobile
npx tsc --noEmit
eas build -p android --profile preview            # APK for the demo

# 4. Verification uploads (Phase 9): MEDIA_ROOT must be writable and backed up
#    curl -F "file=@card.png" -H "Authorization: Bearer $TOKEN" \
#         $API/api/v1/uploads/verification

# 5. Clean-room sanity (new database, migrate → seed → smoke test)
#    Full procedure and expected results: 14-release-candidate-audit.md §2

# 6. Dashboard preview trap
#    VITE_API_BASE_URL must stay empty in production so the console uses /api/v1
#    behind the same origin as the API.
```

## 6. Known limitations (stated, not hidden)

* **No payment gateway, by design.** Fuel sharing is cash between members and is
  never recorded as platform revenue.
* **Map key is optional.** Without it the app uses OpenStreetMap tiles via the server; a bad or expired Geoapify key falls back to OSM. Karachi area centroids remain the search fallback
  and area-name search; nothing else changes.
* **Email delivery needs SMTP.** Without it, verification/reset links are written to
  the API log instead of being sent (`EMAIL_DELIVERY=log`).
* **Push needs an Expo project id.** In-app notifications work regardless; push is
  skipped with a warning when unconfigured.
* **Single confirmed passenger per ride** is a product rule (§9). The schema and the
  services are ready for more seats, but the UI and the partial unique index assume
  one.
* **Reviews cannot be edited**, only hidden by an administrator — deliberate: an
  editable rating is not a reputation.

## 7. Where to go next

1. Read `13-admin-runbook.md` for the day-to-day operations script.
2. `README.md` is the entry point for a new developer.
3. `03-api-contracts.md` is the single source of truth for the HTTP surface — it is
   generated from the same decisions the code enforces.

## 8a. Phase 9 change to the release surface

Verification documents are now uploaded instead of linked (doc 15). Two operational
consequences worth stating before a release:

* `MEDIA_ROOT` must exist, be writable by the API process, and be included in backups —
  a database dump alone does not restore a member's ID photo.
* The upload endpoint is rate limited (10/min per IP) and capped at 5 MB per file, so
  disk growth is bounded by the number of verification attempts, not by traffic.
