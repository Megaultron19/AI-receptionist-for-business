# Installing for a new restaurant

Each restaurant gets its **own server (or VM) or its own directory + Compose project**, its own `.env`,
database volume and domain. Never point two restaurants at the same database or `.env`.

## 1. What you need from the restaurant

- A domain or sub-domain, e.g. `receptionist.spiceroute.in`, with an A record to the server.
- Business details: legal name, address, GSTIN, FSSAI licence, GST rates, service/packaging charges.
- Menu (dishes, prices, sizes, add-ons, prep times, dietary/allergen information they confirm).
- Table list (code, seats, area) and which tables can be pushed together.
- Opening hours, holidays, booking rules (durations, buffer, notice, max party, deposits, cancellation policy).
- Phone number for the AI (Plivo/Twilio), a staff number for transfers, WhatsApp Business number.
- Razorpay account (KYC complete for live mode).
- An Anthropic API key (or set up in their name), billed per usage.

## 2. Server

Ubuntu 24.04 with 2 vCPU / 4 GB RAM is plenty for one restaurant. Install Docker Engine + Compose v2.
Open ports 80 and 443 only.

```bash
sudo mkdir -p /opt/restaurants && cd /opt/restaurants
git clone <your repo> spice-route && cd spice-route
git checkout v1.0.0            # always deploy a tagged release
cp .env.example .env && chmod 600 .env
```

## 3. Fill in `.env`

Required: `DOMAIN`, `COMPOSE_PROJECT_NAME`, `SECRET_KEY` (48+ random chars), `PUBLIC_BASE_URL`
(`https://<DOMAIN>`), `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY`. Provider keys can be added later - the app
runs without them and the **Usage & health** page shows what is missing. Start with **Razorpay test keys**.

## 4. Start

```bash
docker compose up -d --build
docker compose logs -f migrate         # "Running upgrade -> 0001" then exits 0
docker compose exec api python -m app.cli check
docker compose exec api python -m app.cli create-owner --name "Owner Name" --email owner@restaurant.in
```

Open `https://<DOMAIN>/` and sign in. `https://<DOMAIN>/readyz` must return `"ok": true` (database,
migrations and worker all healthy).

Optional: `docker compose exec api python -m app.cli seed-demo` loads a **synthetic** demo restaurant for
training staff; delete or overwrite it before go-live (or import the restaurant's real config file).

## 5. Restaurant setup

See [restaurant-setup.md](restaurant-setup.md): profile & GST, hours & holidays, tables & combinations,
reservation rules, menu, ordering & taxes, AI greeting and approved knowledge, staff accounts.

## 6. Providers

- Phone: [voice.md](voice.md)
- WhatsApp: [whatsapp.md](whatsapp.md)
- Razorpay: [payments.md](payments.md)

## 7. Backups

Add the nightly backup cron (see [operations.md](operations.md#backups)) and copy `backups/` off the server.
Do a test restore once before go-live.

## Go-live checklist

- [ ] `python -m app.cli check` prints `OK` (or only warnings you accept).
- [ ] `/readyz` is `ok: true`; **Usage & health** shows every integration configured and the worker running.
- [ ] Owner + staff accounts created with the right roles; the demo owner (if any) removed.
- [ ] Profile, GSTIN, FSSAI, address, maps link, arrival/pickup instructions filled in.
- [ ] Opening hours and known holidays entered; slot interval, durations, buffer and limits reviewed with the owner.
- [ ] Tables and combinations match the floor; a test booking lands on the expected table.
- [ ] Menu prices, sizes, add-ons, GST rates, charges and discounts checked against a printed bill.
- [ ] AI knowledge reviewed and approved by the restaurant (no unverified claims about allergens or policies).
- [ ] Test call in English and Hindi: booking, change, cancel, menu question, pre-order, transfer to staff.
- [ ] Test WhatsApp chat: booking with QR, waitlist offer, pre-order with edits, payment link, STOP.
- [ ] WhatsApp templates approved in Meta and entered in Settings (needed for reminders and voice-booking confirmations).
- [ ] Razorpay **test** payment completes; refund works; webhook shows `processed` in Usage & health.
- [ ] Switched to Razorpay **live** keys + live webhook secret; one real ₹1 order paid and refunded.
- [ ] Staff trained on: orders board (accept/ready/handed over), QR check-in, handoff queue, callbacks.
- [ ] Nightly backups running and a restore tested; off-server copy configured.
- [ ] Restaurant's privacy notice updated (see [privacy-and-compliance.md](privacy-and-compliance.md)).
