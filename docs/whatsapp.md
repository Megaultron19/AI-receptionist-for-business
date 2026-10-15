# WhatsApp (Business Platform / Cloud API)

## Setup
1. In Meta Business Manager create an app with the **WhatsApp** product; add the restaurant's number.
2. Create a **System User** with access to the app and WhatsApp account; generate a permanent token with
   `whatsapp_business_messaging` and `whatsapp_business_management`.
3. `.env`: `META_ACCESS_TOKEN`, `META_APP_SECRET` (App settings → Basic), `META_PHONE_NUMBER_ID`
   (WhatsApp → API setup), `META_VERIFY_TOKEN` (any random string you choose), `META_GRAPH_VERSION`.
4. WhatsApp → Configuration → Webhook: callback `https://<DOMAIN>/webhooks/whatsapp`, verify token as
   above; subscribe to **messages**.

Webhooks are verified with `X-Hub-Signature-256` over the raw body; each message id is processed once
even when Meta retries; delivery statuses (sent/delivered/read/failed) update the inbox.

## Messaging rules the app enforces
- **24-hour customer service window:** after a customer messages, the AI and staff can reply freely for
  24 hours. Outside it, only **approved templates** can be sent, and only to customers who **opted in**.
- **Consent:** recorded when a caller agrees on the phone, or when the customer agrees in chat
  (`record_whatsapp_consent`). Replying **STOP** opts out.
- If a message can't be sent (no consent, no template, number not on WhatsApp), it is **not** silently
  dropped: the ledger marks it skipped/failed and staff get an alert to contact the customer another way.
- Staff can take over any conversation; the AI stays silent until handed back.

## Templates to create (Settings → WhatsApp templates)
Create these in Meta (category *Utility*), wait for approval, then enter the names. Body variables must be
in this order:

| Setting key | Variables |
|---|---|
| `booking_confirmation` | {{1}} name, {{2}} restaurant, {{3}} booking ref, {{4}} date & time, {{5}} guests, {{6}} QR link |
| `booking_reminder` | {{1}} name, {{2}} restaurant, {{3}} date & time, {{4}} guests, {{5}} booking ref |
| `waitlist_offer` | {{1}} name, {{2}} restaurant, {{3}} date & time, {{4}} guests, {{5}} minutes to confirm |
| `payment_link` | {{1}} name, {{2}} restaurant, {{3}} amount, {{4}} what it is for, {{5}} payment link |
| `order_update` | {{1}} name, {{2}} restaurant, {{3}} order ref, {{4}} status text |
| `cancellation` | {{1}} name, {{2}} restaurant, {{3}} booking ref, {{4}} date & time |
| `staff_alert` | {{1}} alert text |

Example `booking_reminder` body: *Hi {{1}}, a reminder that your table for {{4}} at {{2}} is booked for {{3}}
(ref {{5}}). Reply CANCEL if you can't make it.*

Inside the 24-hour window confirmations are sent as an image (the QR code) with full details; templates
carry the QR **link** instead. Meta's pricing and policies change — check the current WhatsApp Business
Policy and pricing for India before go-live.
