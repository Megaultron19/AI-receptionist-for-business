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

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

## What works so far

- Login for the owner and door staff
- Menu: add, edit, delete dishes, mark out of stock
- Tables: add tables with seat counts, mark unavailable, block time slots for one table or all
- Reservations: real availability, smallest free table assigned, no double bookings even when two requests arrive at once, change, cancel, arrived, no-show
- Settings: restaurant details, opening hours, table time, booking slots
