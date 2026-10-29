# Setting up a new restaurant

Each restaurant gets its own copy of the app on a computer at the restaurant, its own database and its own accounts for WhatsApp, Plivo, Razorpay and Anthropic. Nothing is shared between restaurants except the Cloudflare domain.

Plan for about two hours for the first one, mostly waiting for Meta to approve templates.

## 1. The computer

- Windows 10/11 or a Mac, always on during opening hours and connected to the internet
- Turn off sleep: Windows Settings > System > Power, set "When plugged in, put my device to sleep" to Never. On a Mac: System Settings > Energy, "Prevent automatic sleeping"
- Install Python 3.12 or newer from python.org. On Windows tick "Add python.exe to PATH" in the installer
- Install Node.js LTS from nodejs.org (only needed once, to build the dashboard)

## 2. Install the app

1. Download the code as a zip from GitHub and unzip it somewhere permanent, for example `C:\Receptionist` or `~/Receptionist`.
2. Windows: double click `setup.bat`. Mac: right click `setup.command` > Open.
3. It installs everything, asks for the owner username and password, and puts a "Restaurant Receptionist" icon on the desktop.
4. Add door staff logins with `python -m app.cli add-user door --role staff` from the `backend` folder (use `..\.venv\Scripts\python` on Windows, `../.venv/bin/python` on Mac).

To update later: replace the files with the new version (keep `backend/.env` and `backend/data`) and run setup again. The database is upgraded automatically.

## 3. Cloudflare Tunnel (once per restaurant)

WhatsApp and Plivo need a public https address to reach the restaurant computer. You buy one domain once (for example `myreceptionist.in`) and give each restaurant a subdomain.

1. Add the domain to your Cloudflare account.
2. In Cloudflare Zero Trust > Networks > Tunnels, create a tunnel named after the restaurant, type Cloudflared.
3. Add a public hostname, for example `spicegarden.myreceptionist.in`, service `http://localhost:8000`.
4. Copy the token from the install command Cloudflare shows (the long text after `--token`) into `CLOUDFLARE_TUNNEL_TOKEN` in `backend/.env`.
5. Set `PUBLIC_URL=https://spicegarden.myreceptionist.in`.
6. Download cloudflared for the computer from Cloudflare's downloads page and put it in the app folder, named `cloudflared.exe` on Windows or `cloudflared` on Mac.

You do not install cloudflared as a service. The app starts it when the manager presses Start.

## 4. Accounts and keys

Open `backend/.env` in a text editor. Anything left empty is switched off and shows a cross on the Today page.

### Anthropic

Create an API key in the restaurant's Anthropic console and put it in `ANTHROPIC_API_KEY`.

### WhatsApp

1. In Meta Business, create a WhatsApp app and add the restaurant number.
2. Put the permanent access token, phone number ID and app secret in `.env`. Pick any random text for `WHATSAPP_VERIFY_TOKEN`.
3. Set the webhook URL to `PUBLIC_URL/webhooks/whatsapp` with the same verify token and subscribe to `messages`. The app must be running and started for Meta to verify it.
4. WhatsApp only allows free messages within 24 hours of the customer writing. For bookings made from the dashboard or phone, create a template with an image header and six body values in this order: name, restaurant, booking reference, date and time, guests, table. Put its name in `WHATSAPP_CONFIRMATION_TEMPLATE`.
5. For reminders outside the 24 hour window, create a text template with five body values: name, restaurant, date and time, guests, booking reference. Put its name in `WHATSAPP_REMINDER_TEMPLATE`.

### Plivo

1. Buy an Indian number in the restaurant's Plivo account.
2. Pick a long random text and put it in `PLIVO_WEBHOOK_KEY`.
3. Create a Plivo application with answer URL `PUBLIC_URL/webhooks/plivo/answer?key=YOUR_KEY` and hangup URL `PUBLIC_URL/webhooks/plivo/hangup?key=YOUR_KEY`, both POST, and attach the number to it.
4. Put the staff mobile number in Settings so callers can be transferred.

Callers usually have not messaged the restaurant on WhatsApp, so their booking QR goes out through the confirmation template. Food bills for callers are only sent if they messaged in the last 24 hours, otherwise the Orders page has everything.

### Razorpay

1. In the restaurant's Razorpay dashboard, create API keys and put them in `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
2. That is enough. The app checks unpaid links every minute.
3. Optional, for instant updates: add a webhook to `PUBLIC_URL/webhooks/razorpay` for the `payment_link.paid` event, and put its secret in `RAZORPAY_WEBHOOK_SECRET`.

After changing `.env`, log in as the owner and press Reload keys on the Today page. No restart needed.

## 5. Fill in the restaurant

Log in and set up, in this order:

1. Settings: name, address, phone, staff phone, opening hours, table time, food ready target
2. Tables: every table with its seats
3. Menu: dishes with prices, prep time and other names customers use

## 6. Test before going live

1. Press Start on the Today page. Every item you set up should show a tick.
2. Send "hi" to the WhatsApp number, book a table, and check the QR arrives and the booking appears on Today.
3. Scan the QR on the Check-in page.
4. Order a dish on WhatsApp and pay a small amount with the payment link, check the order turns paid.
5. Call the Plivo number, book a table by voice, ask for a person and check the transfer.
6. Open the Inbox and check nothing is listed under Problems.

## When something goes wrong

- The Today page shows what is not set up, and the Inbox lists failed messages, payment checks and tunnel restarts.
- Logs: `backend/data/app.log` for the app and `backend/data/tunnel.log` for the tunnel.
- The Calls page has the transcript of every call.
- Backups of the database are in `backend/data/backups`. To restore, close the app and copy one over `backend/data/restaurant.db`.
