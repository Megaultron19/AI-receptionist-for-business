# Privacy and compliance notes (India)

This is guidance for setting up an installation, not legal advice, and the software has **not** been
independently audited or certified for compliance with any law or standard. Each restaurant is the data
fiduciary for its customers' data; you (the installer) are typically a service provider to them.

## What personal data is stored (in the restaurant's own database)
Customer phone number, name, language, WhatsApp consent (time and source), bookings, orders, payment
references (no card/UPI details — those stay with Razorpay), WhatsApp/voice transcripts and messages, call
metadata, QR scan logs, staff accounts and an audit log of staff/system actions.

## Built-in controls
- One installation per restaurant: no shared database between businesses.
- Role-based access; owners alone can export or erase customer data and manage staff.
- **Customer data → Export** (access requests) and **Erase** (removes name, phone, messages, transcripts
  and notes; keeps bookings/orders/payments as anonymous records needed for accounts/GST).
- Retention: chat transcripts and message text are cleared after `transcript_retention_days` (default 180);
  webhook payloads after 90 days; finished jobs after 30 days.
- WhatsApp consent tracking, STOP opt-out, no marketing messages are sent by the system.
- The AI discloses that it is an AI assistant. Calls are **not recorded** (only the recognised text of each
  turn is kept as the transcript). If you enable call recording at the provider, inform callers at the start.
- Secrets live in `.env`, never in the browser or the database; application logs avoid customer details.
- HTTPS everywhere (Caddy), secure cookies in production, CSRF protection, rate limits, webhook signatures.

## Things the restaurant should do
- Publish a privacy notice covering the above purposes, retention and contact for requests — the Digital
  Personal Data Protection Act, 2023 and its rules apply to digital personal data of Indian customers.
- Keep allergen/dietary information accurate; the AI repeats it verbatim.
- Follow WhatsApp Business Policy (consent, template categories) and Razorpay's terms.
- TRAI rules on commercial communications apply to promotional calls/SMS — this system makes none.
- Decide where the server is hosted; an Indian region keeps data in-country and lowers call latency.
- Note that conversation text is sent to the configured AI provider (Anthropic) to generate replies; review
  the provider's data-processing terms and mention it in the privacy notice.
