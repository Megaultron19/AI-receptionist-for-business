# Restaurant setup (dashboard)

All of this lives in the installation's database and is edited in the dashboard. Use **Customer data →
Export configuration** to save it as a file (no secrets), and **Import** to load it into another
installation (for example a staging copy, or a second outlet that shares a menu).

## Profile & GST — Settings
Name (and how the voice agent should pronounce it), legal name, address, GST state code, PIN, public phone,
maps link, **GSTIN**, **FSSAI**, timezone (default Asia/Kolkata), arrival and pickup instructions (included
in confirmations).

## Opening hours & holidays — Settings
Per weekday, e.g. `12:00-15:30, 19:00-23:00`. An end time before the start runs past midnight
(`19:00-01:00`). Holidays/closures and special hours are per date. Adding a closure does **not** cancel
existing bookings; check Reservations for that day.

## Tables — Tables page
- Each table: code (`T1`), seats (min–max), area. Inactive tables are never offered.
- Combinations: tables that can be pushed together for larger parties.
- Blocks: take tables out of service for a period (private event, repair). Blocking over an existing
  booking is refused; move the booking first.
- The engine picks the option with the fewest wasted seats, single tables before combinations.

## Reservation rules — Settings
Slot interval, sitting length (plus longer sittings for big parties), cleaning buffer, minimum notice,
how far ahead, party-size limits for AI/online bookings (staff can override), hold time for deposits and
waitlist offers, deposit per guest from a party size, customer cancel/change cutoff, no-show grace period,
reminder times.

## Menu — Menu page
Categories and dishes with Hindi names and **other names customers use** (improves voice/WhatsApp matching:
"PBM", "butter paneer"). Sizes/variants have their own full price. Add-on groups have min/max choices
(e.g. "Sugar: choose 1", "Extras: up to 2"). Dietary tags and allergen text are shown to customers exactly
as entered — the restaurant is responsible for their accuracy. Prep minutes feed the kitchen-time estimate.
"Mark out of stock" is instant and is re-checked when an order is confirmed.

## Ordering, taxes & charges — Settings
- Preparation target (default 5 min), orders cooked in parallel, max open orders, auto-accept.
- Online payment before the kitchen: full, percentage, fixed advance, or nothing (pay at counter).
- Default GST rate (per-dish override available), whether menu prices include GST.
- Charges (packaging, service) as flat paise or basis points, per order type; discounts with minimum
  subtotal. All amounts are computed by the backend in paise; the AI and the browser never set prices.
- Invoice prefix; invoice numbers are sequential per Indian financial year (`SR/26-27/00001`).

Tax rules differ by restaurant (composition scheme, AC/non-AC, hotel restaurants...). Confirm the rates and
the SAC code shown on invoices with the restaurant's accountant.

## AI receptionist — Settings
On/off switch (off = all calls/chats go to staff), languages (English, Hindi via key 2), greetings,
transfer number, staff WhatsApp alert numbers, and **approved information** (parking, kids, policies,
FAQs). The AI only answers from these settings and the live data; keep this text accurate.

## Staff — Staff page
| Role | Can |
|---|---|
| staff | view bookings/orders/menu, QR check-in, mark arrivals, kitchen status |
| receptionist | + create/edit/cancel bookings, waitlist, block tables, orders, WhatsApp inbox, handoff, callbacks, stock toggles |
| manager | + menu, tables, settings, refunds, reports, usage, audit |
| owner | + staff accounts, customer data export/erasure, config export/import |

Changing a role, deactivating, or resetting a password signs that person out everywhere.
