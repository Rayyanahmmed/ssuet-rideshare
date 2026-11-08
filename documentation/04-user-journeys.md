# 4. User Journeys & Screen Map

## 4.1 Personas

| Persona | Goal | Constraint |
|---|---|---|
| **Ali, 6th-semester CS student, Gulshan-e-Iqbal** — drives a Corolla to campus daily | Fill his empty seat, split fuel | Wants nothing to do with payments inside an app |
| **Ahmed, 2nd-semester SE student, Gulistan-e-Johar** — no vehicle | Reach campus at 8 AM reliably | Cannot afford a taxi daily; nervous about sharing a ride with strangers |
| **Dr. Faheem, Associate Professor** — drives from Gulshan | Help students, occasionally share fuel | Cares about verified identities and privacy of his home area |
| **Admin (transport office staff)** | Keep the community safe and verified | Needs queue-style workflows, not dashboards full of noise |

---

## 4.2 Journey A — Publish a ride (Ali, 40 seconds)

```
Home ──["Publish a ride" FAB]──► Step 1 Direction
                                   ├─ Home → University  (destination locked to SSUET)
                                   └─ University → Home  (origin locked to SSUET)
                                 ► Step 2 Location
                                   ├─ Search area (autocomplete)
                                   ├─ Pick on map (pin)
                                   └─ Use my current location
                                 ► Step 3 Date & time (date strip + time wheel, "Tomorrow 8:00 AM")
                                 ► Step 4 Vehicle & fuel
                                   ├─ vehicle card (car/bike, verified badge)
                                   ├─ 1 seat (fixed, honest about the rule)
                                   └─ Free  •  Share fuel → Fixed / Expected / Negotiable + amount
                                 ► Step 5 Note (optional) ──► Review & Publish
Publish ──► success sheet "Your journey is live" + [View ride] [Share]
        └─► appears instantly in Explore for other users
```

Guardrails: max ~3 fields per step, progress dots persistent, draft persists in
Zustand (killed app → restore), validation per step before "Continue", and the
publish button disabled until valid.

## 4.3 Journey B — Find and join a ride (Ahmed, 25 seconds)

```
Home ──► "Where are you heading?" search or [Home → University] chip
      ──► Explore list: RideCards sorted by departure time
            card = avatar + name + ✅ verified + ★4.8 + car/bike icon
                 + "Gulistan-e-Johar → SSUET" + "Tomorrow 8:00 AM"
                 + [FREE] or [Fuel share ~Rs.150] + "1 seat"
      ──► Ride details: driver card, vehicle, approximate pickup area,
          map preview (route), fuel terms, note, reviews (last 3)
      ──► [Request to join] → optional message → PENDING
            └─ if the seat was taken meanwhile → toast "This ride has just been
               taken" + list refreshes (§9)
      ──► Notification: "Fatima accepted your request"
      ──► Trip screen: meeting point unlocked, phone visible, [Chat] enabled
```

## 4.4 Journey C — Driver triages requests (Fatima)

```
Notification "Ahmed wants to join your ride" ──► My Rides › Published › Requests
  request row: avatar, name, department, ✅ verified, ★rating, message
  [Accept] ──► confirmation dialog: "Accepting confirms 1 seat; other pending
              requests will be declined automatically"
           ──► trip created, chat opened, both notified, ride becomes MATCHED
  [Reject] ──► optional note, requester notified kindly
```

## 4.5 Journey D — Trip day

```
T-2h  push: "Your ride to SSUET leaves in 2 hours"
T-0   driver: [Start trip]        → trip IN_PROGRESS, ride IN_PROGRESS
      both:   chat to coordinate at the exact meeting point
T+45  either: [Mark completed]    → both confirm → COMPLETED
      ──► counters increment; both prompted to rate
      ──► review sheet: 5 stars + optional note ("She was on time and polite")
      ──► profile averages recompute instantly
```

## 4.6 Journey E — Something goes wrong (safety, §15)

```
Trip screen or public profile ──► ⋯ menu
   ├─ Report user → category (behaviour / fake profile / misleading ride /
   │                harassment / safety) + description → complaint OPEN
   └─ Block user  → you will never be matched again; existing chat locked
Cancellation: either side may cancel before start; the other party is notified
immediately with the reason. Repeated cancellations surface in the admin
complaint queue.
```

## 4.7 Journey F — Admin verification (transport office)

```
Login (role must be ADMIN) ──► Verification Requests queue
  card: name, role, department, submitted ID value, document thumbnail,
        email domain flag
  [Verify] → user badge ON, notification sent, admin_actions row written
  [Reject] → reason required, user can resubmit
```

## 4.8 Screen map (mobile)

```
(auth)   Splash → Onboarding (3 slides) → Login / Signup / Forgot password
(tabs)   Home · Explore · Publish · My Rides · Profile
stack    ride/[id]  trip/[id]  chat/[conversationId]  profile/[userId]
         notifications  vehicles/  vehicles/new  settings  report/[userId]
         verification-status   reviews/[userId]
```

## 4.9 Home screen composition (the money screen)

```
┌──────────────────────────────────────────────┐
│  Assalam-o-Alaikum, Ahmed            🔔 (3)  │  greeting + avatar + bell
│  Ready for tomorrow's commute?               │
├──────────────────────────────────────────────┤
│  ▸ SSUET · University Road, Karachi          │  university card (branded,
│    University-bound journeys near you        │  static, from /meta)
├──────────────────────────────────────────────┤
│  [Search area or driver…]        🔍          │  search
│  [Home → University] [University → Home]     │  direction chips
│  [Tomorrow ▾] [8 AM–9 AM ▾] [Free] [All ▾]   │  quick filters
├──────────────────────────────────────────────┤
│  Upcoming trip                               │  confirmed trip card
│  Fatima · Tomorrow 8:15 AM · GBR → SSUET     │  → [Chat] [Details]
├──────────────────────────────────────────────┤
│  Available near you            See all ›     │  3 RideCards
└──────────────────────────────────────────────┘
      [  Publish a ride  ]  ← primary FAB/CTA
   🏠 Home  🧭 Explore  ➕ Publish  🚗 My Rides  👤 Profile
```

States that must exist on **every** list screen: skeleton (3 cards shimmering),
empty ("No rides match yet — try widening your time window" + [Publish a ride]),
error ("Couldn't load rides" + [Retry]), and pull-to-refresh.
