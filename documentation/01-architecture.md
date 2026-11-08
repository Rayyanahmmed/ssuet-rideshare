# 1. System Architecture — SSUET RideShare

> University ride **pooling** platform for Sir Syed University of Engineering &
> Technology (SSUET), Karachi. Students and teachers publish the journeys they
> already drive; other members of the community request to travel along.

---

## 1.1 Product principles

| Principle | Consequence in the design |
|---|---|
| Pooling, not taxi booking | Drivers publish journeys they were already making. There is no fare, no dispatch, no payment. |
| Verified community only | Accounts carry `verification_status`; unverified users can browse but cannot publish or request. |
| One ride = one passenger | Enforced by a **partial unique index** in PostgreSQL, not only by application code (§9). |
| Privacy by default | Only coarse area labels are public. Exact meeting point + phone are released after a request is accepted. |
| Fuel money is not platform money | Contributions are an offline agreement between two people. No gateway, no wallet, no commission. |
| Offline-first friendliness | Maps are optional: when a key is absent the app falls back to area search. |

---

## 1.2 Three components, one contract

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  Mobile app                 │        │  Admin dashboard             │
│  React Native + Expo        │        │  React + Vite + Tailwind     │
│  TypeScript, Expo Router    │        │  TanStack Query, Recharts    │
│  (students & teachers)      │        │  (browser, RBAC = ADMIN)     │
└──────────────┬──────────────┘        └───────────────┬──────────────┘
               │  HTTPS / REST (JSON)                   │
               │  WSS / WebSocket (chat)                │ HTTPS / REST (JSON)
               └───────────────────┬────────────────────┘
                                   ▼
                 ┌───────────────────────────────────────┐
                 │  FastAPI backend (Python 3.11+)       │
                 │  ─────────────────────────────────    │
                 │  api/v1  → routers (thin)             │
                 │  services → business rules            │
                 │  models  → SQLAlchemy ORM             │
                 │  core    → config, security, errors   │
                 │  realtime→ WebSocket hub (chat)       │
                 │  notifications → in-app + Expo push   │
                 └───────────────┬───────────────────────┘
                                 ▼
                 ┌───────────────────────────────────────┐
                 │  PostgreSQL 16                        │
                 │  Alembic owns the schema              │
                 │  database/schema.prisma = design doc  │
                 └───────────────────────────────────────┘
```

**Golden rule: the backend is the only source of truth.** The mobile app never
sends "the user id is X" or "I am the driver" as authority — the JWT identifies
the caller and every ownership/permission check is re-derived server-side.

---

## 1.3 Layer responsibilities (backend)

| Layer | Path | Responsibility | Must NOT contain |
|---|---|---|---|
| Routers | `app/api/v1/*` | HTTP parsing, status codes, response models, dependencies | Business rules, raw SQL |
| Schemas | `app/schemas/*` | Pydantic request/response contracts (Zod mirrors these on mobile) | DB access |
| Services | `app/services/*` | Transactions, seat reservation, state machines, notifications | `HTTPException` |
| Models | `app/models/*` | Tables, relationships, DB-level constraints | Business logic beyond invariants |
| Core | `app/core/*` | Settings, security primitives, logging, error envelope | Domain rules |
| Realtime | `app/realtime/*` | WebSocket auth, connection rooms per conversation | Persistence |

Why a service layer at all? Because "accept a request" touches five rows (request,
ride, trip, conversation, notification) and must be one transaction. Routers stay
readable; the invariant lives in one place and is unit-testable.

---

## 1.4 Request lifecycle (accept a ride request)

```
Passenger            API                    Service                        DB
   │  POST /requests/{id}/accept              │                            │
   ├──────────────────►│                      │                            │
   │                   │ auth dep: JWT→user   │                            │
   │                   ├─────────────────────►│                            │
   │                   │                      │ BEGIN                      │
   │                   │                      ├───────────────────────────►│
   │                   │                      │ SELECT ride FOR UPDATE     │
   │                   │                      ├───────────────────────────►│
   │                   │                      │ guard: caller is driver?   │
   │                   │                      │ guard: ride OPEN + seat>0? │
   │                   │                      │ guard: request PENDING?    │
   │                   │                      │ ride→MATCHED, seats=0      │
   │                   │                      │ request→ACCEPTED           │
   │                   │                      │ INSERT trip  ──────────────┼──► partial unique index
   │                   │                      │ INSERT conversation        │    blocks a 2nd live trip
   │                   │                      │ INSERT notification x2     │
   │                   │                      │ COMMIT                     │
   │◄──────────────────┤ 200 TripOut          │                            │
   │                   │  (push + WS event broadcast as background task)   │
```

Any `IntegrityError` on the partial index is translated to
`409 RIDE_NOT_AVAILABLE` so the losing racer gets an honest message.

---

## 1.5 Mobile architecture

```
mobile/
  app/                     # Expo Router file-based routes
    (auth)/login.tsx, signup.tsx, forgot-password.tsx
    (tabs)/index.tsx       # Home
    (tabs)/explore.tsx     # Explore Rides
    (tabs)/publish.tsx     # Publish Ride
    (tabs)/my-rides.tsx    # My Rides (5 tabs)
    (tabs)/profile.tsx     # Profile
    ride/[id].tsx          # Journey details
    trip/[id].tsx          # Confirmed trip + chat
  src/
    api/        # axios client, endpoint functions (typed)
    components/ # design-system primitives (Card, Button, Badge, RideCard…)
    hooks/      # TanStack Query hooks per resource
    store/      # Zustand: auth session, filters, draft ride
    theme/      # colours, spacing, typography, shadows
    lib/        # zod schemas, formatters, map helpers
```

State ownership:

* **Server state** → TanStack Query (rides, trips, chat history, notifications).
* **Session** → Zustand + `expo-secure-store` (access + refresh token only).
* **Ephemeral UI** → local component state; ride draft → Zustand so the
  multi-step publish flow survives navigation.

---

## 1.6 Admin dashboard architecture

```
admin-dashboard/
  src/
    api/         # TanStack Query wrappers (X-Request-ID, error envelope aware)
    components/  # layout (Sidebar, Topbar), cards, tables, charts
    pages/       # Dashboard, Users, Verifications, Vehicles, Rides, Trips,
                 # Reports, Suspended, Analytics, Settings
    routes/      # React Router with a ProtectedRoute(role=ADMIN)
    store/       # auth (in-memory access token + refresh via httpOnly-safe flow)
```

Admin tokens are **never** hardcoded in the bundle; login goes to
`POST /api/v1/auth/login` and the role claim must be `ADMIN`.

---

## 1.7 Cross-cutting decisions

| Concern | Decision | Rationale |
|---|---|---|
| API versioning | `/api/v1` prefix for everything | future breaking changes without a rewrite |
| Error shape | `{"error": {"code","message","details"}}` | one parser in both clients |
| Pagination | cursor for feeds (`?cursor=&limit=`), page/page_size for admin tables | feed stability vs. admin jump-to-page |
| IDs | UUID v4 generated in Python | no enumeration of users/rides |
| Time | store UTC (`timestamptz`), render in `Asia/Karachi` | avoids DST/summertime bugs |
| Money | `NUMERIC(10,2)` for a *voluntary* contribution only | never floats for money |
| Geo | `lat/lng` doubles + area label; radius filter in SQL | PostGIS not required for a city-scale MVP |
| Chat | WebSocket per conversation, room = `conversation_id` | authorization checked on connect and on every send |
| Soft delete | `deleted_at` on users, vehicles, rides | auditability + FK integrity |
| Rate limiting | SlowAPI on `/auth/login`, `/auth/register`, `/auth/forgot-password`, `/requests` | brute-force and spam protection |

---

## 1.8 Environments

| | Development | Preview (FYP demo) | Production |
|---|---|---|---|
| DB | Docker PostgreSQL 16 (or SQLite for zero-setup) | same as dev | managed PostgreSQL |
| API | `uvicorn --reload` on `0.0.0.0:8000` | same | container, 2+ workers |
| Mobile | Expo Go / dev client | EAS **preview** APK | EAS **production** AAB |
| Admin | Vite dev server | Vercel/Netlify static | same + HTTPS only |
| Secrets | `.env` files (git-ignored) | EAS secrets + `.env` | platform secret store |

---

## 1.9 Deliberately out of scope (MVP)

Payments/commissions, live GPS tracking during a trip, multi-passenger pooling,
recurring ride templates, in-app calling, rating appeals, i18n (Urdu). Each has a
documented extension point so it can be added without schema surgery.
