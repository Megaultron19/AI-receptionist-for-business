# Operations: backups, upgrades, monitoring, troubleshooting

All commands run from the restaurant's installation directory (e.g. `/opt/restaurants/spice-route`).

## Backups
```bash
./deploy/backup.sh                     # pg_dump (custom format) into ./backups, verified, 14 days kept
crontab -e                             # 0 3 * * * cd /opt/restaurants/spice-route && ./deploy/backup.sh >> backups/backup.log 2>&1
```
Copy `backups/` off the server daily (rclone to S3-compatible storage, or another machine). Back up `.env`
separately in a password manager — it holds the secrets and is **not** in the database dump.

## Restore
```bash
./deploy/restore.sh backups/resto-20261016-030000.dump   # stops api/worker, replaces the DB, re-runs migrations
```
Test a restore before go-live and after major upgrades (restore into a scratch Compose project:
`docker compose -p spice-route-restore-test ...`).

## Upgrades
1. Read `CHANGELOG.md` for the target version (required steps, new settings, migration notes).
2. `./deploy/backup.sh`
3. `git fetch --tags && git checkout vX.Y.Z`
4. Add any new variables from `.env.example` to `.env`.
5. `docker compose up -d --build` — the `migrate` service applies database migrations before the API and
   worker start; they won't start if a migration fails.
6. Check `/readyz` and **Usage & health**. To roll back: check out the previous tag and restore the backup
   taken in step 2 (migrations are forward-only).

Versioning: `MAJOR.MINOR.PATCH`. Patch/minor releases keep the database compatible and only add migrations;
a major release may require manual steps listed in the changelog. Never skip `migrate`.

## Monitoring
- `GET /healthz` (process up) and `GET /readyz` (database, migrations, **worker heartbeat**) — point an
  uptime monitor at `/readyz`.
- **Usage & health** page: each integration's last success/failure and consecutive failures, job queue
  (queued/dead/overdue), webhook processing in the last 24 h, usage and estimated costs.
- **Overview → Alerts**: failed jobs, payment mismatches/late payments, failed refunds, skipped
  notifications, AI outages, handoffs, callbacks, new orders. Errors and handoffs are also sent to the staff
  WhatsApp numbers (template `staff_alert`).
- Logs: `docker compose logs -f api worker` — JSON lines with a `request_id` matching the `X-Request-ID`
  response header. Set `SENTRY_DSN` for error tracking (PII sending is off).

## Troubleshooting
| Symptom | Check |
|---|---|
| `/readyz` worker false | `docker compose ps worker`, `docker compose logs worker`; restart it. Reminders, payment links and messages wait in the queue until it runs. |
| Calls get "not in service"/403 | `PUBLIC_BASE_URL` must equal the URL configured at Plivo/Twilio (https, no trailing slash); auth token correct. |
| Calls answered but AI never replies | `ANTHROPIC_API_KEY`, alerts `ai_unavailable`, Usage & health → llm. Callers are transferred or a callback is logged meanwhile. |
| WhatsApp verify fails | `META_VERIFY_TOKEN` matches Meta's field exactly. |
| WhatsApp messages not answered | Webhook subscribed to `messages`; `META_APP_SECRET` correct (403s in logs = signature mismatch); conversation not in staff mode. |
| Reminders not delivered | Customer opted in? `booking_reminder` template approved and entered? See Notifications in alerts. |
| Payment paid but order still waiting | **Payments → Check status** forces a verification; webhook events in Usage & health; the reconcile job runs every 5 min. |
| "No table is free" though tables look empty | Blocks, buffer time, table min/max seats, combinations, opening hours for the full sitting length. |
| Job shows *dead* | Alert includes the error; fix the cause (credentials, provider outage) — the business record is unchanged, re-trigger the action from the dashboard. |
