# admin-dashboard/ — SSUET RideShare Admin Console

React 18 + TypeScript + Vite + Tailwind + React Router + TanStack Query (+ Recharts
in Phase 6).

## Run

```bash
npm install
cp .env.example .env
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` → `http://127.0.0.1:8000`, so no CORS setup is
needed. Start the backend first.

## Sign in

Use the administrator provisioned from the backend `.env`
(`ADMIN_EMAIL` / `ADMIN_PASSWORD`). After the first boot set
`ADMIN_BOOTSTRAP_ENABLED=false`.

## What exists

* `/login` — real authentication against `POST /api/v1/auth/login`.
* `ProtectedRoute` — token → `GET /auth/me` → **role must be ADMIN**; otherwise the
  console redirects to `/login` and revokes the session.
* Session store in `sessionStorage` (cleared on tab close) with silent refresh and
  server-side logout.
* Sidebar per §16 with the live administrator identity, plus a functional Logout.
* Dashboard reporting real API / database / maps status; Phase 6 modules are
  labelled placeholders — no fabricated statistics.

## Security notes

* No credential, token or API key is ever compiled into this bundle (§17).
* Production hardening (documented): move the refresh token to an httpOnly,
  SameSite=Strict cookie issued by the API.
