# Restaurant Receptionist

Phone and WhatsApp receptionist for restaurants, with a simple dashboard for the restaurant team.
Each restaurant runs its own copy on its own computer with its own database and settings.

## Run it for development (your own computer)

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

## What it does

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
- WhatsApp reminder a few hours before each booking (3 by default), sent once. Customers reply to change or cancel
- Waitlist: when nothing is free, customers can join it. When a table frees up they get a WhatsApp message to book it
- Inbox: chats handed to staff, with replies from the dashboard and a button to hand back to the AI. Updates when customers book, change, cancel, join the waitlist, order or pay. Problems such as failed messages are listed too
- Desktop icon on Windows and Mac starts everything. The manager logs in and presses Start on the Today page
- Start also opens the Cloudflare Tunnel so WhatsApp, Plivo and Razorpay can reach the restaurant computer, and restarts it if it drops
- Stop turns the receptionist off: WhatsApp messages are ignored and callers hear the closed message
- Reload keys button for the owner after editing `backend/.env`, no restart needed
- Door staff can seat walk-ins from the Tables page. The table is blocked for the usual table time so it can't be booked, with a button to free it when the guests leave. Refused if the table has a booking coming up
- Daily database backup in `backend/data/backups`, last 14 days kept
- Login is locked for 15 minutes after 5 wrong passwords. Session cookies are secure when used over the tunnel

## Setting up a new restaurant

See [docs/SETUP.md](docs/SETUP.md).
