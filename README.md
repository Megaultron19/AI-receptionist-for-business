# AI Restaurant Receptionist

A self-hosted AI receptionist for restaurants, cafés and food businesses. It answers **phone calls** and
**WhatsApp**, books and manages **tables**, takes **editable food pre-orders**, computes **GST bills**,
collects payments through **Razorpay**, sends **QR-code confirmations**, and gives staff a **dashboard**.

**One installation per restaurant.** Every restaurant runs its own copy: its own database, credentials,
phone/WhatsApp numbers, menu, tables, payments, logs, backups and staff accounts. There is no shared
backend, tenant system or central billing. You maintain this one codebase and deploy it per customer.

## What it does

| Area | Highlights |
|---|---|
| Voice | Plivo (Indian numbers) or Twilio; English + Hindi (press 2); speech or keypad; barge-in; transfer to staff, callback requests, graceful fallback when the AI is down; call log with outcomes and duration |
| WhatsApp | Official Cloud API; webhook verification + signature checks; dedup of retried events; 24-hour window, consent and approved-template rules; delivery statuses; STOP opt-out; human takeover |
| Reservations | Tables, combinations, blocks; party-size rules, durations, buffers, hours with past-midnight intervals, holidays; **PostgreSQL exclusion constraint makes double-booking impossible**; alternatives; reschedule/cancel; deposits; waitlist promotion; reminders; no-show tracking |
| Menu & orders | Categories, dishes, Hindi names/aliases, variants, add-on groups, dietary/allergen info, stock toggles; ambiguity-aware dish matching; editable drafts; backend bill calculation (discounts, charges, CGST/SGST, tax-inclusive pricing); kitchen-load quotes vs a 5-minute target; strict order state machine; GST invoice numbering |
| Payments | Razorpay payment links; raw-body webhook signature checks; idempotent processing; every "paid" independently verified with Razorpay; failed/expired/late payments; refunds; reconciliation job |
| QR | Hashed, revocable, expiring tokens; staff check-in for bookings and pickups; duplicate-scan handling; scan audit |
| Dashboard | Next.js + Tailwind; role-based (owner, manager, receptionist, staff), enforced by the API |
| Operations | Usage + cost estimates, integration health, audit log, reports, data export/erasure, retention purge, config export/import, backups |

## Repository layout

```
backend/            FastAPI app (Python 3.13), Alembic migrations, pytest suite
  app/<module>/     auth, restaurant, tables, reservations, menu, orders, payments, qr,
                    notifications, conversations, whatsapp, voice, ai, reporting, core
frontend/           Next.js dashboard (static export), vitest + Playwright tests
deploy/             Dockerfiles, Caddyfile, backup/restore scripts, synthetic sample restaurant
docker-compose.yml  One Compose project = one restaurant
docs/               Installation, setup, providers, operations, privacy, architecture
```

## Quick start (development)

Requires Python 3.13, Node 22 and PostgreSQL 16.

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
createdb resto && cp .env.example backend/.env   # set SECRET_KEY, DATABASE_URL=postgresql+psycopg://...@localhost:5432/resto
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.cli seed-demo                       # synthetic demo restaurant
../.venv/bin/python -m app.cli create-owner --name You --email you@example.com
../.venv/bin/uvicorn app.main:app --reload --port 8000 &       # API
../.venv/bin/python -m app.cli worker &                         # background jobs
cd ../frontend && npm install && npm run dev                     # dashboard on http://localhost:3000
```

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q          # needs a PostgreSQL database "resto_test"
cd frontend && npm test                                  # unit tests
cd frontend && npm run build && npm run e2e              # Playwright, starts its own API + database
```

External providers (LLM, WhatsApp, Razorpay, telephony) are simulated in tests. See
[docs/testing.md](docs/testing.md) for what is covered and what still needs sandbox credentials.

## Deploying for a restaurant

Follow [docs/installation.md](docs/installation.md): server, `.env`, `docker compose up`, restaurant setup,
providers, test-mode checks and the go-live checklist. Day-two operations (backups, upgrades,
troubleshooting) are in [docs/operations.md](docs/operations.md).
