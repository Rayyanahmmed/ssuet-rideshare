# Documentation index

Read in this order. Each document is meant to be usable on its own during the FYP
defence.

| # | File | What it answers |
|---|---|---|
| 1 | [01-architecture.md](01-architecture.md) | How the three components fit together, layer responsibilities, request lifecycle, cross-cutting decisions |
| 2 | [02-database-design.md](02-database-design.md) | ER diagram, every table and constraint, status machines, transaction strategy, index plan |
| 3 | [03-api-contracts.md](03-api-contracts.md) | Every endpoint with filters, error codes and rate limits; what is implemented vs. planned |
| 4 | [04-user-journeys.md](04-user-journeys.md) | Personas, the six journeys, screen map, home-screen composition, required UI states |
| 5 | [05-roadmap-and-progress.md](05-roadmap-and-progress.md) | Phase-by-phase deliverables, live progress board, definition of done, Phase 1 verification log |
| 6 | [06-risks-and-external-setup.md](06-risks-and-external-setup.md) | External APIs, Google key restriction, risks with mitigations, push/socket and trust notes |
| 7 | [07-phase3-ride-system.md](07-phase3-ride-system.md) | Phase 3 — vehicles, publishing, Explore, requests, concurrency & privacy decisions |
| 8 | [08-phase4-trip-lifecycle.md](08-phase4-trip-lifecycle.md) | Phase 4 — trip state machine, both-side completion, no-show, housekeeping jobs |
| 9 | [09-phase5-chat-notifications.md](09-phase5-chat-notifications.md) | Phase 5 — WebSocket chat protocol, notifications, Expo push delivery |
| 10 | [10-phase6-admin-dashboard.md](10-phase6-admin-dashboard.md) | Phase 6 — admin API, authorisation, console modules, audit trail |
| 11 | [11-phase7-trust-quality.md](11-phase7-trust-quality.md) | Phase 7 — reviews, reports & blocking, privacy/IDOR hardening |
| 12 | [12-phase8-testing-and-release.md](12-phase8-testing-and-release.md) | Phase 8 — test strategy, coverage, load sanity, Android release, device checklist |
| 13 | [13-admin-runbook.md](13-admin-runbook.md) | Day-to-day operations for the ride-share office |
| 14 | [14-release-candidate-audit.md](14-release-candidate-audit.md) | v1.0.0 audit: API contracts vs docs, clean-room boot, secrets, stale copy, verdict |
| 15 | [15-phase9-media-pipeline.md](15-phase9-media-pipeline.md) | Phase 9 verification uploads: storage, security rules, live evidence, configuration |
| 16 | [16-phase10-vehicle-documents.md](16-phase10-vehicle-documents.md) | Phase 10 vehicle documents, admin Proof column, orphan sweep, storage overview |
| 17 | [17-production-deployment.md](17-production-deployment.md) | Phase 11 deployment: systemd, nginx, backups, smoke test, PostgreSQL parity, CI |
| 18 | [18-observability-and-load.md](18-observability-and-load.md) | Phase 12 request correlation, `/admin/health`, monitoring + alerts, measured capacity |
| 19 | [19-profile-photos.md](19-profile-photos.md) | Phase 13 profile photos: semi-public visibility, uploads, avatars in app and console |
| 20 | [20-image-normalisation.md](20-image-normalisation.md) | Phase 14 EXIF/GPS stripping, orientation, 512 px WebP, cached thumbnails, bomb guard |
| 21 | [21-photo-moderation.md](21-photo-moderation.md) | Phase 15 reporting a profile photo, pinned evidence, resolve-and-remove |
| 22 | [22-operations-handbook.md](22-operations-handbook.md) · [**PDF**](22-operations-handbook.pdf) | **Phase 16** the printable handover: day one, the daily routine, incident playbooks, backups, release procedure, limits, sign-off |
| 23 | [23-run-it-yourself.md](23-run-it-yourself.md) | **Start here on your own machine** — local setup (Windows/macOS/Linux), running the app on a phone with Expo Go, and building the APK |
| 24 | [24-environment-and-commands.md](24-environment-and-commands.md) | **Every env variable and command** — what to put in the three `.env` files, what is optional (maps / SMTP / push), the full command list, five wiring checks |
| 25 | [25-deployment-commands.md](25-deployment-commands.md) | **Copy-paste deployment runbook** — fresh Ubuntu VPS: base system, PostgreSQL, code, env, migrations, systemd, console, nginx + TLS, cron, app release, verification, rollback |

Supporting artefacts:

| File | Contents |
|---|---|
| [testing/coverage.txt](testing/coverage.txt) | statement coverage per module (94% total) |
| [testing/load-sanity.txt](testing/load-sanity.txt) | Explore read-path latency at concurrency 20 |
| [screenshots/](screenshots) | admin console screens used in the phase documents, incl. the Phase 9 upload viewer |

Repository-level setup instructions live in [`../README.md`](../README.md).
