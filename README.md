# Restaurant Receptionist

Phone and WhatsApp receptionist for restaurants, with a simple dashboard for the restaurant team.
Each restaurant runs its own copy on its own computer with its own database and settings.

## Run it for development

Needs Python 3.12+ and Node 22.

```
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
cd backend
../.venv/bin/python -m app.cli add-user owner --role owner
../.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and log in.

Copy `backend/.env.example` to `backend/.env` and fill in the keys you have. Anything left empty is simply switched off.

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

## What works so far

- Login for the owner and door staff
- Menu: add, edit, delete dishes, mark out of stock
- Tables: add tables with seat counts, mark unavailable, block time slots for one table or all
- Reservations: real availability, smallest free table assigned, no double bookings even when two requests arrive at once, change, cancel, arrived, no-show
- Settings: restaurant details, opening hours, table time, booking slots
- WhatsApp: customers chat to book, change or cancel a table, ask about the menu, or ask for a person
- Booking confirmation on WhatsApp with a QR code, restaurant name, booking reference, date and time, guests and table
- Bookings made from the dashboard also get the WhatsApp confirmation
- Check-in page for the door: scan the QR code with a scanner gun or the camera, duplicate and wrong-day scans are refused
- Failed AI replies hand the chat to staff, and WhatsApp send failures are recorded
- Food orders from WhatsApp or the dashboard, linked to a booking or not. Customers name dishes in their own words and get an itemized bill
- Orders can be edited until they are paid. Prices are fixed when the dish is added, so a later menu price change does not touch existing bills
- Orders page: start by time for pre-orders, preparing, ready, served, mark paid for cash
- The food time promise (default 5 minutes after arrival) is only given when the slowest dish can actually be ready by then
- Razorpay payment link sent with the bill. An order is only marked paid after the server asks Razorpay and the amount matches. Repeated webhooks or checks never mark it twice or send two receipts
- Editing an order cancels the old payment link and sends a new one. If the old link was already paid, the edit is refused
- Paid in cash button cancels any open payment link so the customer can't pay twice
- New columns are added to an existing database automatically on start, so updating a restaurant keeps its data
- Phone receptionist on Plivo: answers in English or Hindi, checks real availability, books, changes and cancels, takes food pre-orders, and sends the QR confirmation on WhatsApp after the call
- Outside opening hours callers hear "the restaurant is closed, please call later" in English and Hindi
- Callers asking for a person, or any AI failure, are transferred to the staff phone from Settings. Without one, the call is marked "needs callback"
- Calls page with the outcome and transcript of every call

## Plivo setup

1. Buy an Indian number in the restaurant's Plivo account.
2. Pick a long random text and put it in `PLIVO_WEBHOOK_KEY`.
3. Create a Plivo application with answer URL `PUBLIC_URL/webhooks/plivo/answer?key=YOUR_KEY` and hangup URL `PUBLIC_URL/webhooks/plivo/hangup?key=YOUR_KEY`, both POST, and attach the number to it.
4. Put the staff mobile number in Settings so callers can be transferred.

Callers usually have not messaged the restaurant on WhatsApp, so their booking QR goes out through the confirmation template. Food bills for callers are only sent if they messaged in the last 24 hours, otherwise the Orders page has everything.

## Razorpay setup

1. In the restaurant's Razorpay dashboard, create API keys and put them in `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
2. That is enough. The app checks unpaid links every minute.
3. Optional, for instant updates: add a webhook to `PUBLIC_URL/webhooks/razorpay` for the `payment_link.paid` event, and put its secret in `RAZORPAY_WEBHOOK_SECRET`.

## WhatsApp setup

1. In Meta Business, create a WhatsApp app and add the restaurant number.
2. Put the permanent access token, phone number ID and app secret in `.env`. Pick any random text for `WHATSAPP_VERIFY_TOKEN`.
3. Set the webhook URL to `PUBLIC_URL/webhooks/whatsapp` with the same verify token and subscribe to `messages`.
4. WhatsApp only allows free messages within 24 hours of the customer writing. For bookings made from the dashboard or phone, create a template with an image header and six body values in this order: name, restaurant, booking reference, date and time, guests, table. Put its name in `WHATSAPP_CONFIRMATION_TEMPLATE`.
