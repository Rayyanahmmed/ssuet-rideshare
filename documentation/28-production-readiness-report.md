# 28 · Production readiness report

This report records one complete, clean run of the project. The ZIP was extracted into an empty
folder, dependencies were installed from the lock files, and every check ran against a
production-mode API with a fresh PostgreSQL database. Nothing was reused from the developer's
working copy.

Not covered here: the live Render, Neon and Vercel accounts, and the EAS APK build. Those need
your accounts. Steps are in `27-deploy-vercel-render.md`.

## 1. Results (final run)

| Area | Check | Result |
|---|---|---|
| Backend | full pytest suite (463 tests) | **463 passed** |
| Database | `alembic upgrade head` on empty PostgreSQL 17 (9 revisions) | OK |
| Database | `alembic check` (models match migrations) | No drift |
| API | production smoke (`backend/scripts/prod_smoke.py`) | **25 / 25** |
| Admin | TypeScript + production build | OK |
| Admin | browser: sign-in, Users, reset code, reset screen | **7 / 7** (`mobile/scripts/e2e-reset-admin.py`) |
| Web app | TypeScript | OK |
| Web app | map check (`verify-map.mjs`) | **38 / 38** |
| Web app | navigation check (`verify-navigation.mjs`) | **68 pass, 0 fail** |
| Web app | browser E2E (`e2e-web.py`): sign-in, tabs, back navigation, map tiles, APK button | **14 / 14, 0 console errors** |
| Web app | profile photo renders (`e2e-photo-web.py`) | PASS |
| Security | every API route without a token (110 operations) | Only 13 public, all intentional |

Public routes (by design): APK link, forgot / reset password, register, login, logout, refresh,
verify email, health (2), maps config, map tile proxy, `/meta`.

## 2. Problems found and fixed in this run

1. **Access tokens survived a password reset for up to 30 minutes.** Refresh tokens were revoked,
   but JWT access tokens are stateless. Now the user record stores `sessions_revoked_at`
   (migration `e3c9b7d1a426`), and tokens issued earlier are refused at once. Tokens carry
   millisecond issue time (`iat_ms`), so a token issued in the same second is still handled
   correctly. Covered by a new test.
2. **Reset-password screen was missing in the app.** The forgot-password flow sent an email whose
   link opened no screen. Added `app/(auth)/reset-password.tsx`, which accepts the emailed link or a
   code typed in. The admin fallback (code from the console) uses the same screen.
3. **Profile photos did not load on the web app.** The web build sends `<img>` tags, which cannot
   carry the bearer token, so every photo returned 401 and the initials were shown instead. The
   web now fetches the photo with the token and shows it from a blob URL, as the admin console
   already did. Native APK builds are unchanged.
4. **API docs were public in production** (`/docs`, `/openapi.json`). They are now off when
   `ENVIRONMENT=production`.
5. **Stale text:** the APK fallback URL pointed at an old domain, the admin error message named
   port 8000, the README still described a Google Maps key, and the start guide and two docstrings
   described disk storage. All corrected.

## 3. How the test was run (repeatable)

```bash
# 1. fresh folder
mkdir deploy-test && cd deploy-test && unzip ../SSUET-RideShare-v1.0.0.zip
# 2. backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
# 3. clean database, production settings
DATABASE_URL=postgresql+psycopg://... .venv/bin/alembic upgrade head
ENVIRONMENT=production ... .venv/bin/python -m uvicorn app.main:app --port 8100
# 4. test data only (never in production): ENVIRONMENT=development python -m scripts.seed
# 5. web and admin builds with the API address
EXPO_PUBLIC_API_URL=https://<api>/api/v1 npx expo export -p web -c        # in mobile/
VITE_API_BASE_URL=https://<api>/api/v1 npm run build                       # in admin-dashboard/
# 6. checks
python backend/scripts/prod_smoke.py https://<api>/api/v1 https://<admin>
python mobile/scripts/e2e-reset-admin.py <admin-url> <web-url> <api-url>
python mobile/scripts/e2e-photo-web.py <web-url>
python mobile/scripts/e2e-web.py --base <web-url> --api <api-url>
```

Run the browser checks with a minute between them. Login is limited to 30 attempts per minute per
IP, and password reset to 5 per minute (see section 4).

## 4. Decisions for you (open)

- **Login rate limit: changed to 30 per minute per IP** (was 10). Students on one campus Wi-Fi
  share a public IP. Done.
- **Reset-code limit (5 per minute per IP).** The same applies to password resets. Admin-issued
  codes are not limited.
- **Email delivery.** Set up Brevo as described in guide 27, or accept the admin reset code only.
- **APK.** The build needs your Expo login. Confirm the Render address used in `eas.json`
  (`ssuet-rideshare-api.onrender.com`) matches the name Render gives you.

## 5. Known limits (not blockers)

- Render's free plan sleeps after 15 minutes. Use UptimeRobot (guide 27, step 8).
- Neon's free plan has 1 GB of storage. Profile photos are about 100 KB each.
- The admin "media" health warning reads the disk of the container, which is not used for new
  uploads. It can show a free-space warning that does not matter. Harmless.
- Native APK behaviour (photos with the header, the reset screen, the map in Expo Go) was checked
  by code and type checks. The web tests cover the same screens in a browser.
- The web bundle contains a sample address text from the testing server panel. It is only shown
  when `EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`, which the production build sets to `0`.
- Doc 26 (chat location change) and a running Expo dev server are still pending from earlier work.

## 6. Verdict

The code is ready to deploy. Everything the project can check locally passes from a clean
extraction, on PostgreSQL, with production settings. What remains needs your accounts (Neon,
Render, Vercel, Expo, Brevo) and the decisions in section 4.
