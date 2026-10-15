# Architecture

A **modular monolith** per restaurant installation:

```
            Plivo / Twilio ──► /voice/*        ┐
   Meta WhatsApp Cloud API ──► /webhooks/whatsapp ├─► FastAPI (backend/app) ──► PostgreSQL (source of truth)
          Razorpay webhooks ──► /webhooks/razorpay┘        │  ▲
   Staff browser ──► Caddy ──► static dashboard + /api/*   ▼  │
                                                    worker (python -m app.cli worker) ─► Razorpay / WhatsApp / LLM
```

| Module | Responsibility |
|---|---|
| `core` | audit log, alerts, usage, integration health, Postgres job queue, logging, rate limits |
| `auth` | staff accounts, sessions, roles/permissions |
| `restaurant` | settings, hours, holidays, rules |
| `tables` / `reservations` | tables, combinations, blocks; transactional booking engine, waitlist, holds |
| `menu` / `orders` | menu, dish matching; drafts, billing, kitchen quotes, order state machine, invoices |
| `payments` | Razorpay client, links, verification, refunds, reconciliation |
| `qr` | tokens, check-in, public QR page |
| `notifications` | WhatsApp notification ledger (window/consent/template rules) and message composition |
| `conversations` | conversations, inbox messages, calls, callbacks, handoff |
| `ai` | provider-independent LLM interface (`llm.py`), Claude adapter, prompt, tools, agent loop |
| `voice` | telephony provider abstraction (Plivo, Twilio) and call flow |
| `whatsapp` | Cloud API client, webhook ingestion |
| `reporting` | usage/health/reports, data export/erasure, config export/import, retention |

## Key decisions
- **Double-booking prevention in the database.** `table_allocations` has a GiST exclusion constraint
  (`table_id =`, `period &&`, `WHERE active`). Bookings, reschedules, waitlist offers and staff blocks all
  insert allocations inside savepoints; a concurrent conflict raises `23P01` and the engine tries the next
  table. Tested with 20 parallel requests.
- **Postgres job queue instead of Celery/Redis.** Jobs are inserted in the same transaction as the change
  that needs them (outbox pattern), workers claim with `FOR UPDATE SKIP LOCKED`, dedupe keys make enqueueing
  idempotent, failures back off exponentially (15 s → 30 min cap) and dead jobs raise alerts. One fewer
  service per restaurant; Redis is never a source of truth. Swap for Celery if one installation ever
  outgrows it.
- **The AI only acts through tools** that call the same validated services as the dashboard; tool errors
  are returned to the model to relay. Provider transcripts are stored verbatim and append-only.
- **Payments are verified by fetching from Razorpay**, never trusted from webhook bodies or messages.
- **Static dashboard export** behind Caddy: no Node.js process in production.

## Known limits
- Voice uses turn-based speech gather, not full-duplex streaming.
- WhatsApp voice notes/images get a "please type" reply (no transcription yet).
- Rate limiting is per API process (one process per installation by default).
- Dish images are URLs (no upload/S3 integration yet).
- A confirmed booking that grows past the deposit threshold is not asked for a new deposit.
