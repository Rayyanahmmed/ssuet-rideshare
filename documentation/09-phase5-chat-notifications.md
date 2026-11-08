# 9. Phase 5 — Trip chat & notifications (implementation record)

Two-way communication between the two members of a trip, and a notification
system that never loses an event even when push delivery is unavailable.

---

## 9.1 Chat — one write path, two transports

A conversation is created **automatically** when a driver accepts a request
(Phase 3). From then on the same `chat_service` functions serve both transports:

| Transport | Endpoint | Used when |
|---|---|---|
| REST | `GET/POST /chat/conversations/{id}/messages` | always available; the mobile app falls back to it if the socket cannot connect |
| WebSocket | `WS /api/v1/chat/ws/{conversation_id}?token=<access JWT>` | preferred; adds live delivery, typing, presence and read receipts |

Because both call `chat_service.create_message`, there is exactly one place that
persists a message, updates the conversation preview, and notifies the other
member — a socket message and an HTTP message cannot diverge.

### REST surface

| Method & path | Purpose |
|---|---|
| `GET /chat/conversations` | My conversations, newest activity first, with `unread_count` each and `unread_total` |
| `GET /chat/conversations/{id}` | One conversation (participants or admin only) |
| `GET /chat/conversations/{id}/messages?cursor=&limit=` | History, **newest first**; `next_cursor` walks backwards through time |
| `POST /chat/conversations/{id}/messages` | Send (`{ "body": "…" }`, 1–2000 chars, trimmed, blanks rejected) |
| `POST /chat/conversations/{id}/read` | Mark every incoming message read; returns how many |

### Socket protocol

```
client → server   {"type":"message","body":"…"}   {"type":"typing","is_typing":true}
                  {"type":"read"}                 {"type":"ping"}

server → client   {"type":"ready", conversation_id, user_id, online[], participants[],
                   counterpart{id,full_name}, last_message_at}
                  {"type":"message","message":MessageOut}
                  {"type":"typing","user_id","is_typing"}
                  {"type":"read","user_id","read_at","messages_marked_read"}
                  {"type":"presence","online":[user_id…]}
                  {"type":"error","code","message"}   {"type":"pong"}
```

Handshake rules:

* The access token comes from `?token=` **or** an `Authorization: Bearer` header.
* Authentication is re-derived server-side exactly like REST (`_load_socket_user`):
  expired token, deleted account, suspended account → close code **1008** with a
  human reason, never an accepted socket.
* The room is validated independently (`_load_room`): only the trip's driver and
  passenger may join. A third member is refused even with a valid token.
* Presence is derived from the room registry — no extra table, no stale "online"
  rows after a crash.

### Details worth knowing

* **`is_mine` is viewer-specific.** A shared broadcast would tell the receiver
  their own message was theirs, so each connected user gets their own copy with
  the flag computed for them (`_deliver_message`). Caught by a test.
* **Message order is exact.** Two messages written inside the same microsecond
  would otherwise fall back to a random UUID tiebreak; `create_message` nudges
  `created_at` forward by 1 µs when needed, so insertion order == display order
  and the `(created_at, id)` cursor stays stable.
* **Blocked pairs cannot message** (`403 BLOCKED`) and **cancelled trips are
  read-only** (`409`) — the history stays, new messages stop.
* **Multi-device**: the room is keyed by user, so a member with two handsets gets
  the message on both.
* The hub is in-process (`app/services/chat_hub.py`). For a multi-worker
  deployment, swap the registry for Redis pub/sub — the wire protocol and REST
  API do not change (documented in `documentation/06`).

---

## 9.2 Notifications — persisted first, pushed second

Every business event already writes a row through
`notification_service.create_notification_from_template`. Phase 5 adds reading,
badges and Expo push on top of that same table.

| Method & path | Purpose |
|---|---|
| `GET /notifications?unread_only=&cursor=&limit=` | History + `unread_count` |
| `GET /notifications/unread-count` | Badge count (polled by the app) |
| `POST /notifications/{id}/read` · `POST /notifications/read-all` | Mark read |
| `GET /notifications/devices` · `POST /notifications/devices` · `DELETE /notifications/devices/{token}` | Expo token lifecycle |

New templates in Phase 5: `NEW_MESSAGE`; `TRIP_STARTED`, `TRIP_AWAITING_CONFIRMATION`,
`TRIP_NO_SHOW` were added in Phase 4.

### The delivery contract (§12)

1. **The row is the source of truth.** If Expo is down, the notification is still
   in the database and the in-app bell works.
2. **Push happens after the commit.** Notifications are created inside service
   transactions (usually `commit=False`), so each one is queued on the session
   (`push_service.queue_push`). The request boundary (`get_db` teardown) and the
   chat socket flush the queue — a notification that was rolled back is silently
   dropped instead of being announced. (An earlier attempt to use SQLAlchemy's
   `after_commit` hook failed by design: SQL is not allowed in that state.)
3. **Failures never break a request.** Network errors are logged, the row keeps
   `push_sent_at = NULL`, and a later flush retries.
4. **Dead devices are unregistered.** Expo's `DeviceNotRegistered` ticket response
   deactivates that token automatically.
5. **A handset that changes accounts is re-pointed**, not duplicated — and the
   previous account can no longer deactivate it.

Push is disabled automatically in the test environment (`ENVIRONMENT=test`) and
when `EXPO_PUSH_ENABLED=false`; notification rows are still written in both cases.

---

## 9.3 Mobile surface added

| Screen / module | File | Notes |
|---|---|---|
| Chat transport | `src/api/chat.ts` | Typed REST + `chatSocketUrl()` deriving `ws(s)://…/api/v1/chat/ws/…` from the configured API URL |
| Chat screen | `app/chat/[id].tsx` | Inverted list, optimistic send, reconnect with exponential backoff, typing indicator, presence, read receipts, older-page loading, "Say salam" empty state |
| Messages list | `app/chats.tsx` | All trip conversations with unread badges + online dots |
| Notifications | `app/notifications.tsx` | Unread styling, mark-one/mark-all, pull-to-refresh, pagination, deep links to chat / trip / My Rides |
| Push lifecycle | `src/lib/push.ts` | Permission → Expo token → `POST /notifications/devices`; unregisters on sign-out |
| Home | `app/(tabs)/index.tsx` | Bell with live unread badge, "Messages" quick action, and the next confirmed trip from real data |
| Trip screen | `app/trip/[id].tsx` | "Open chat" button wired to the trip's `conversation_id` |

Transport behaviour on the phone:

* If the socket cannot connect, the header says so, messages still send over REST,
  and the app retries with backoff (1 s → 15 s) — no dead composer.
* Close code `1008` stops retrying and shows "live chat unavailable" (a token
  problem, not a network blip).
* Sending is optimistic: the bubble appears immediately and is reconciled with the
  server copy (matched by body + sender), or rolled back with the draft restored
  and an error banner if the send fails.

---

## 9.4 Verification

```bash
cd backend && python -m pytest          # 202 passed (164 + 22 chat + 16 notifications)
cd mobile  && npx tsc --noEmit          # 0 errors
              npx expo export --platform android   # 4.13 MB HBC, bundles clean
```

`tests/test_chat.py` (22) covers conversation creation on accept, outsider 403,
authentication 401, unknown conversation 404, message round-trip with preview and
unread counts, read receipts, backwards cursor pagination, blank/overlong/trimmed
bodies, blocked pairs, cancelled-trip read-only, and the socket: handshake state,
two-way delivery with per-viewer `is_mine`, presence join/leave, typing, read
frames, non-participant and bad-token rejection (1008), header auth, ping/pong and
unknown frames.

`tests/test_notifications.py` (16) covers inbox privacy, unread counts, mark
one/all, cursor pagination, invalid cursor, device register/revive/deactivate,
token re-pointing between accounts, payload building (inactive + already-pushed
skipped), successful dispatch with dead-token cleanup, network failure resilience,
post-commit flush, rolled-back notification never pushed, and that chat/trip
events produce the right notification types.

**Live proof against a real uvicorn server (two browsers' worth of tokens):**

```
ready            ok, counterpart resolved
presence         2 online
sender is_mine   True  |  receiver is_mine  False
typing           relayed
read             marked 1 → sender's message read_at set
REST history     200, 1 message, preview updated
devices          201 ExponentPushToken[…]
pytest           202 passed
```

---

## 9.5 External setup still required by the owner (§13)

| Item | Why | Where |
|---|---|---|
| `EXPO_PUSH_ENABLED=true` (default) | Turns on Expo dispatch | `backend/.env` |
| EAS project id (`EAS_PROJECT_ID`) | Expo cannot mint a push token without it | `mobile/.env` |
| FCM credentials (`google-services.json` / FCM V1 key) | **Android push in a dev/EAS build** needs Firebase Cloud Messaging; Expo Go cannot receive remote push | EAS project settings |
| Physical device | Notification permission + real token only exist on hardware | — |

Without these, everything except the OS-level push banner still works: the in-app
bell, notification list, unread counts and all chat features are fully functional.

## 9.6 Deferred

| Item | Phase |
|---|---|
| Redis pub/sub for multi-worker sockets | 8 (documented upgrade path) |
| "Message read" push suppression while the chat is open | 8 polish |
| Admin chat inspection (moderation) | 6, read-only via conversation id |
| Rich attachments / images in chat | out of MVP scope |
