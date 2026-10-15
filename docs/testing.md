# Testing

| Suite | Command | What it covers |
|---|---|---|
| Backend (pytest, real PostgreSQL) | `cd backend && ../.venv/bin/python -m pytest -q` | Concurrent booking race (20 threads), table capacity/combinations, buffers, hours/holidays/midnight, slot/notice/advance rules, blocks, status machine, reschedule atomicity, waitlist promotion and expiry, reminders; menu matching and ambiguity, order editing, bill maths (GST split, discounts, charges, tax-inclusive), minimum payments, kitchen quotes; Razorpay link idempotency under failures, webhook signature, duplicate/forged/out-of-order events, failed→success, expiry, late payment refund, deposits; QR validation, revocation, expiry, duplicate scans, pickup checks; notification window/consent/template policy and retry idempotency; handoff, callbacks, alerts; voice signature checks, silence, Hindi, AI outage transfer/callback, transfer tool; WhatsApp verification, dedup, statuses, STOP, human mode, send-failure retry; LLM adapter request shape; RBAC/CSRF/rate limit; settings validation; migrations vs models; readiness; config export/import; privacy export/erasure; retention purge; every periodic job |
| End-to-end flows (pytest) | `tests/test_e2e_flows.py` | (1) WhatsApp booking → QR → staff check-in; (2) voice pre-order with ambiguity, edits, server bill → Razorpay link → verified payment → acceptance → ready → QR pickup; (3) WhatsApp cancellation → waitlist offer → YES → confirmed with QR |
| Frontend unit (vitest) | `cd frontend && npm test` | money/time formatting in the restaurant timezone, CSRF header, error handling |
| Dashboard E2E (Playwright) | `cd frontend && npm run build && npm run e2e` | login, booking with live slots, timeline, check-in, double-booking refusal, menu stock toggle, phone order with server bill through the kitchen flow, role-restricted navigation + API 403, settings validation, holidays, staff creation |

External providers are simulated (scripted LLM, fake WhatsApp/Razorpay APIs, signed Plivo/Twilio requests).
**Not yet run against live sandboxes:** Razorpay test mode, Meta WhatsApp test number, Plivo/Twilio test
calls, Anthropic API with a real key. Do these with real credentials during installation (see the
go-live checklist).
