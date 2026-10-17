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

## WhatsApp setup

1. In Meta Business, create a WhatsApp app and add the restaurant number.
2. Put the permanent access token, phone number ID and app secret in `.env`. Pick any random text for `WHATSAPP_VERIFY_TOKEN`.
3. Set the webhook URL to `PUBLIC_URL/webhooks/whatsapp` with the same verify token and subscribe to `messages`.
4. WhatsApp only allows free messages within 24 hours of the customer writing. For bookings made from the dashboard or phone, create a template with an image header and six body values in this order: name, restaurant, booking reference, date and time, guests, table. Put its name in `WHATSAPP_CONFIRMATION_TEMPLATE`.
