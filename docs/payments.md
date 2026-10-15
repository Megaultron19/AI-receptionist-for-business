# Razorpay

## Test mode first
1. Razorpay Dashboard → switch to **Test mode** → Settings → API Keys → generate `rzp_test_...` key/secret.
2. Settings → Webhooks → add `https://<DOMAIN>/webhooks/razorpay`, set a secret, select events:
   `payment_link.paid`, `payment_link.expired`, `payment_link.cancelled`, `payment.authorized`,
   `payment.captured`, `payment.failed`, `refund.processed`, `refund.failed`, `refund.created`.
3. `.env`: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`; restart (`docker compose up -d`).
4. Place a test order, pay with Razorpay's test card/UPI, refund it from **Payments**.

## Going live
Complete KYC, generate **live** keys, create the same webhook in live mode with a new secret, update `.env`,
restart, then make one real small payment and refund it. `app.cli check` warns if production still uses
`rzp_test_` keys.

## How payments are handled
- Amounts come only from server-computed bills/deposits (in paise). Minimum ₹1.
- One Razorpay **Payment Link** per payment; our payment reference is the link's `reference_id`, so a
  retried job finds the existing link instead of creating a second one.
- Webhooks are verified with `X-Razorpay-Signature` over the raw body, stored once per event id, then
  processed by the worker. A payment is marked **paid only after the app fetches the link from Razorpay and
  sees it fully paid** — a forged, duplicated or out-of-order webhook cannot mark anything paid.
- A reconciliation job re-checks open links and pending refunds every 5 minutes (covers lost webhooks).
- Paid → the order is **submitted** to the kitchen; acceptance by the restaurant is a separate step.
- Payments for an order that was edited/cancelled meanwhile, or a deposit for an expired hold, are
  refunded automatically and staff are alerted.
- Refunds (full/partial) from **Payments**; status follows Razorpay's refund webhooks.
- No card data ever touches this system; secrets stay server-side.

If WhatsApp can't be used for a customer, the payment link is created with Razorpay's own SMS notification.
