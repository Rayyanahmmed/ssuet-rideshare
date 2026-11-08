# 6. External Services, Risks & Mitigations

## 6.1 External APIs / services

| Service | Needed for | Free tier | Env var(s) | Owner action |
|---|---|---|---|---|
| **OpenStreetMap tiles** (default) | map imagery, pin picking | free for light traffic | none — proxied by the backend | nothing; attribution is shown automatically |
| **Geoapify / MapTiler** (optional) | sharper styles, higher limits | free tier each | **database only** — set in the console → **Map API** | paste a key once; rotate it there whenever it expires |
| **Expo EAS** | APK/AAB builds | free tier | EAS account login | `eas build:configure`, keystore generation |
| **Expo Push (FCM)** | push notifications | free | FCM credentials in EAS | upload FCM v1 service account |
| **SMTP provider** | verification / reset emails | e.g. Brevo/Gmail app password | `SMTP_*` (Phase 2) | provide credentials |
| **PostgreSQL** | persistence | local Docker / Neon free | `DATABASE_URL` | local or managed instance |

### Map key handling (§13) — why there is no key in the app any more
1. The APK contains **no** map credential. It renders a WebView map whose tiles come from
   `/api/v1/maps/tiles/{z}/{x}/{y}.png`, where the backend attaches the provider key.
2. The key lives in the `app_settings` table, encrypted with a Fernet key derived from
   `JWT_SECRET_KEY`; the API never returns it, only `has_key: true/false`.
3. Rotating or replacing the key is a **console** action (Map API tab) — every installed app
   follows on its next tile request. No rebuild, no `.env` edit, no redeploy.
4. If a provider key is missing or rejected, `GET /meta` reports
   `features.maps_configured: false`, the app falls back to area lists, and the console's
   **Test connection** button explains the exact rejection (e.g. `401 Invalid apiKey`).
5. `MAP_PROVIDER` / `GEOAPIFY_API_KEY` in `backend/.env` only seed a fresh install.

## 6.2 Technical risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Two passengers reserve the last seat simultaneously | double-booked trip, broken trust | `SELECT … FOR UPDATE` + partial unique index on `trips(ride_id) WHERE status <> 'CANCELLED'`; `IntegrityError` → `409 RIDE_NOT_AVAILABLE` (already implemented & tested) |
| R2 | Users without university email cannot be verified | blocked onboarding | manual admin verification path + `Verification` audit table (§4) |
| R3 | Fake accounts / impersonation | safety | verified badge, vehicle verification, reports, suspension, admin action log |
| R4 | Privacy leak (home address, phone) | real-world harm | two-tier location model; phone/coords released only after acceptance; serializers are explicit allow-lists |
| R5 | Map costs / key abuse | budget blowout | restricted keys, server-side Directions only, area fallback without key |
| R6 | Chat abuse / unauthorized access | privacy breach | JWT on WebSocket handshake, room membership = trip participants, re-checked per message |
| R7 | Refresh-token theft | account takeover | SHA-256 at rest, rotation on use, reuse detection revokes the chain |
| R8 | Admin credential leakage | full compromise | env-only bootstrap, Argon2 hash, never in React bundle, `ADMIN_BOOTSTRAP_ENABLED=false` after first boot, production secret validation fails fast |
| R9 | SQLite/PostgreSQL divergence | "works on my machine" | single SQLAlchemy model set, Alembic migration verified against both dialects, pytest runs the same constraints |
| R10 | Prisma & Alembic drifting apart | schema confusion | Prisma is a read-only artifact; Alembic is the only migrator; `alembic check` in CI |
| R11 | Timezone bugs (PKT vs UTC) | wrong departure times | store UTC, format in `Asia/Karachi` at the edge only |
| R12 | EAS build fails at the deadline | no APK for the defence | build `preview` APK from Phase 4 onward, not only at the end; physical-device testing each phase |
| R13 | Over-scoping (payments, live GPS) | unfinished core | explicitly out of scope (§1.9) with documented extension points |
| R14 | Free-text area search quality | poor discovery | curated Karachi area list + optional Places autocomplete + radius filter on lat/lng |
| R15 | Uploaded ID documents (personal data) on disk | a leaked file identifies a student; a lost file blocks verification | no public static mount — every read is authorised (owner or admin); content validated by magic bytes; 5 MB cap; `media/` gitignored; back up `MEDIA_ROOT` with the database (doc 13 §8) |
| R16 | Unbounded media growth | disk fills, API stops writing | 10 uploads/min per IP + 5 MB per file; per-member footprint ~200–400 KB; unused uploads swept after `MEDIA_ORPHAN_RETENTION_DAYS` (Phase 10, doc 16); `GET /admin/media` reports files/bytes/orphans for monthly review |

## 6.3 Open questions for the project owner (answer before Phase 3)

1. Should a driver be allowed to publish **more than one** open ride per day (e.g. morning and evening)? *(Current design: yes.)*
2. Cancellation penalty policy: after how many passenger cancellations does the admin review the account? *(Proposal: 3 in 30 days → flag.)*
3. Should teachers get any priority in request ordering? *(Proposal: no, first-come-first-served.)*
4. Is a `.edu.pk` domain available for all students, or is student-ID upload the primary verification path? *(Affects Phase 2 effort.)*
5. EAS/FCM/Google Maps accounts — who owns them for the FYP defence?

---

## Push notifications & chat at scale (Phase 5 notes)

| Topic | Current state | What the owner must do |
|---|---|---|
| Expo push token | `expo-notifications` installed, permission + token flow implemented | Set `EAS_PROJECT_ID` and add FCM credentials (Android) in the EAS project; Expo Go cannot receive remote push |
| Backend dispatch | `app/services/push_service.py` posts to `https://exp.host/--/api/v2/push/send`, batched at 100 per request, after the DB commit | Set `EXPO_PUSH_ENABLED=false` to disable; the in-app bell keeps working |
| Dead tokens | `DeviceNotRegistered` deactivates the token automatically | none |
| Chat sockets | In-process room registry (`app/services/chat_hub.py`) | For more than one API worker, replace the registry with Redis pub/sub and point every worker at the same Redis — the WebSocket protocol and REST API stay identical |
| Socket auth | Access JWT in `?token=` or an `Authorization` header; closed with code 1008 on failure | Ensure reverse proxies forward `Upgrade`/`Connection` headers (nginx: `proxy_set_header Upgrade $http_upgrade;`) |
| Message ordering | Server nudges `created_at` by 1 µs when two messages share a timestamp | none |

## Admin console risk notes (Phase 6)

| Risk | Mitigation in place |
| --- | --- |
| Admin token stolen / left in an open browser | Tokens live in `sessionStorage` (cleared when the tab closes), the API re-reads role **and** `account_status` from the database on every request, so a suspended or demoted admin loses access instantly |
| Rogue administrator acting without accountability | Every mutation appends an immutable `admin_actions` row (actor, target, action, note, timestamp) shown in Analytics → Action history |
| Admin accidentally suspending another admin | Rejected server-side with `409` — the console disables the button as a hint, but the API is the authority |
| Dashboard showing invented numbers | All figures come from SQL aggregates in `/admin/dashboard` and `/admin/analytics`; empty queues render explanatory empty states, never sample rows |
| Secrets leaking into the browser | `/admin/settings` exposes booleans only; a test greps the serialised payload for `jwt`, `password` and `secret` |
| Destructive action with no explanation to the member | Rejection, suspension and force-cancel require a reason, which is stored and delivered as a notification |
| Console built against a stale API | `tsc` + `npm run build` in CI, plus the live endpoint sweep documented in `documentation/10-phase6-admin-dashboard.md` |

**Production checklist for the console:** serve it over HTTPS behind the same reverse
proxy as the API, keep `VITE_API_BASE_URL` relative (`/api/v1`) so no host is baked
into the bundle, rotate `ADMIN_PASSWORD` after the first bootstrap, and set
`ADMIN_BOOTSTRAP_ENABLED=false`.

## Trust & moderation notes (Phase 7)

| Risk | Mitigation in place |
| --- | --- |
| Retaliatory or fake ratings | Only people who completed a trip together can rate, once per side; the database enforces it too. Comments are trimmed and length-bounded, and an admin can hide a review (which recomputes the average) with an audited reason. |
| Review-bombing a driver | A rating requires a **completed** trip between the two accounts, so volume is naturally capped by real journeys. |
| Report aimed at a stranger | The subject is derived from the trip/ride and validated against real participation; a mismatched `reported_user_id` is rejected with `422`. |
| Complaint queue flooding | One open report per reporter→subject pair (`409`), plus a `5/minute` rate limit. |
| Reporter left in the dark | Resolution writes `REPORT_RESOLVED` with the office's note, which is also returned by `GET /reports/{id}`. |
| Personal data leaking in payloads | `tests/test_security.py` walks Explore, ride detail and public-profile payloads and fails on phone, email, home address, home coordinates or meeting-point keys; `401/403/404` behaviour on every id-taking endpoint is asserted in the same suite. |
| Blocked member re-appearing | Explore, request creation and chat all exclude blocked pairs on both directions; covered by tests and by the chat 403 path. |
