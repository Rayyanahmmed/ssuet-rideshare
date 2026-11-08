# 21 · Phase 15 — photo moderation

**Status:** complete. A member can report a profile picture; the exact file is pinned as
evidence; the ride-share office decides, and the decision can take the picture down in
the same step — without destroying what was complained about.

```
backend$  python -m pytest tests/test_photo_moderation.py     # 20 passed (421 total, 94 %)
live:     Ali reports Fatima's photo → PROFILE_PHOTO/OPEN → admin resolves + removes → photo gone,
          evidence still readable by the office, member notified "Profile photo removed"
```

---

## 1. The gap

Doc 19 §6 and doc 20 §5 both ended on the same line: *an administrator can see every
face and suspend an account, but a member cannot report a specific picture.* That is the
one part of the photo story that was still missing, and it is the part that matters
operationally — the first thing a real complaint does is point at an image.

## 2. What was built, and the two decisions that shaped it

**A photo report is an ordinary report.** The `reports` table already carries a reporter,
a subject, a category, a description, a status, a handler and a resolution note, and the
console already has a queue, notifications and an audit trail for it. Rather than invent
a parallel moderation system, Phase 15 adds a category (`PROFILE_PHOTO`), a reason
(`photo_reason`) and a link to the file (`reported_photo_asset_id`). The office learns
one queue, not two.

**Evidence is pinned and never deleted.** The moment a report is filed, the current asset
id is copied onto the report. Two consequences, both deliberate:

| Scenario | Behaviour |
| --- | --- |
| Member uploads a new photo while the report is open | the old file is **kept** — `set_profile_photo` refuses to delete a reported asset |
| Admin removes the photo as part of the decision | the member's pointer is cleared and the current file deleted, but a *reported* file stays readable by administrators |
| Orphan sweep runs | reported assets are a fourth reference set, so the sweep keeps them too |

Without this, a member could make a complaint unanswerable by uploading something else
— and an administrator's decision would leave no record of what they looked at.

## 3. The flow

```
member sees a photo
  → POST /users/{id}/photo/report   {reason, description}
      ├─ 404 if the member has no photo
      ├─ 422 on self-report ("to change your own photo, upload another one")
      ├─ 409 if an open photo report already exists from this member
      └─ 201 → report OPEN, asset pinned, reporter acknowledged, every admin notified
  → console: Reports & complaints → "Photo · Not a real person" chip
      ├─ evidence thumbnail in the handling dialog
      ├─ outcome (under review / resolve / dismiss) + note
      └─ optional "Also remove the photo"
  → PATCH /admin/reports/{id} {status, resolution_note, remove_photo: true}
      ├─ clears the member's photo, notifies them ("Profile photo removed")
      ├─ audit: REMOVE_PROFILE_PHOTO + UPDATE_REPORT in admin_actions
      └─ keeps the reported file as evidence
```

Refusals worth noting: `remove_photo` on a non-photo report is a **422**, so an
administrator cannot delete a picture while resolving a complaint that was never about a
picture.

## 4. Where members meet it

* **Mobile**: a flag button on the driver card in ride detail (only on somebody else's
  ride, and only when they actually have a photo) opens a dedicated screen —
  `app/report-photo/[userId].tsx` — with four reasons, a description box and the same
  `ApiError` handling as the trip report screen.
* **Console**: the queue row names the reason, the dialog shows the pinned picture, and
  the removal is a single checkbox on the decision.

## 5. Evidence

Through nginx + TLS against the live stack:

```
fatima photo restored → 201
report through nginx → 201 · PROFILE_PHOTO · OPEN
```

Console (Playwright, dev server, 0 console errors):

```
reports queue rows: 2
photo report row present: true
row text: Ali Raza · Fatima Noor · Photo · Not a real person · "This looks like an illustration…"
evidence preview shown: true   ·  evidence images decoded: 1
remove-photo switch present after choosing Resolve: true
```

Screenshot: `documentation/screenshots/phase15-moderation.png`.

Service-level proof of the decision path (from the smoke run):

```
resolve → 200 RESOLVED
fatima photo now: None
evidence still readable by admin: 200 · 4340 bytes
member cannot read old evidence as their photo: 404
fatima notifications: ['Profile photo removed', 'Trip cancelled', 'Report received']
```

## 6. What this still does not do

* **No automatic triage.** Nothing pre-screens a photo; every decision is human. At a
  campus pilot's volume that is a feature, not a gap — but it is the honest limit.
* **No "report a photo in chat".** Chat images do not exist in this product (messages are
  text), so there is nothing to report there.
* **No member-side appeal.** The decision notifies the member and they may upload a
  different picture, but there is no formal appeal flow; the office is reachable through
  the same report channel.
* **Suspension is still separate.** Removing a photo never suspends an account — that
  stays an explicit second action on the member's dossier, by design (doc 13).
