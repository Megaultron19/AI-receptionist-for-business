# Restaurant Receptionist

An AI receptionist for restaurants that answers phone calls and WhatsApp in English and Hindi, books tables without double bookings, takes food pre-orders with itemized bills, collects payment through Razorpay and sends QR booking confirmations. The restaurant team runs everything from a simple dashboard.

Each restaurant gets its own installation on a computer at the restaurant, with its own database, its own WhatsApp, Plivo, Razorpay and Anthropic accounts, and its own dashboard. The code is the same for every restaurant.

## What it does

**Phone (Plivo)**
- Answers calls in English or Hindi, checks real availability, books, changes and cancels tables
- Takes food pre-orders by voice
- Sends the QR booking confirmation on WhatsApp after the call
- Transfers to the staff phone when the caller asks for a person or something goes wrong
- Outside opening hours callers hear "the restaurant is closed, please call later"
- Calls page with the outcome and transcript of every call

**WhatsApp**
- Bookings, changes and cancellations, menu questions, food pre-orders
- Booking confirmation with a QR code, restaurant name, booking reference, date and time, guests and table
- Reminder a few hours before the booking (3 by default)
- Waitlist: when nothing is free the customer can join it, and the first person waiting is booked automatically when a table frees up. One table, one booking, never two
- Any chat can be handed to staff, who reply from the dashboard

**Food orders and payment**
- Customers name dishes in their own words and get an itemized bill
- Orders can be edited until they are paid. Prices are fixed when the dish is added
- Razorpay payment link with the bill. An order is only marked paid after the server checks with Razorpay and the amount matches. Repeated payment notifications never mark it twice
- Paid in cash button for the counter
- The food time promise (5 minutes after arrival by default) is only given when the slowest dish can actually be ready

**Dashboard**
- Today: Start and Stop for the receptionist, with ticks for what is set up, and today's bookings
- Inbox: chats waiting for staff, updates when customers book, change, cancel, order or pay, and any problems
- Reservations with waitlist, Orders, Calls, Menu with prices and stock, Settings
- Tables: seats per table, mark unavailable, block time slots, seat walk-ins
- Check-in for the door: scan the QR with a scanner gun or camera, duplicate and wrong-day scans are refused
- Logins: the owner adds door staff and other logins, resets their passwords and turns logins off. Everyone can change their own password, and anyone given a temporary password must pick their own on the next login
- Forgotten owner password: `reset-password.bat` or `reset-password.command` on the restaurant computer gives a temporary one

**Reliability and safety**
- No double bookings, even when two requests arrive at the same moment
- Nothing is confirmed to a customer before it is saved
- Failed messages, payment checks and calls are recorded in the Inbox
- Keys are kept in `backend/.env`, never in the code
- Daily database backup, last 14 days kept
- Login locked for 15 minutes after 5 wrong passwords

## Running at a restaurant

A desktop icon on Windows or Mac starts everything. The manager logs in and presses Start, which also opens a Cloudflare Tunnel so WhatsApp, Plivo and Razorpay can reach the restaurant computer.

Setting up a new restaurant step by step: [docs/SETUP.md](docs/SETUP.md)

## Development

Needs Python 3.12+ and Node 22.

```
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
cd backend
../.venv/bin/python -m app.cli add-user owner --role owner
../.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and log in. Copy `backend/.env.example` to `backend/.env` and fill in the keys you have. Anything left empty is switched off.

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

Built with FastAPI, SQLite, Next.js, Claude (Anthropic), Plivo, the WhatsApp Cloud API, Razorpay and Cloudflare Tunnel.
