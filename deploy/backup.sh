#!/usr/bin/env bash
# Nightly database backup for ONE restaurant installation (run from its directory, e.g. via cron):
#   0 3 * * * cd /opt/restaurants/spice-route && ./deploy/backup.sh >> backups/backup.log 2>&1
# Keeps 14 daily dumps locally. Copy ./backups off the server too (S3/rclone/another machine).
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP_DAYS=${KEEP_DAYS:-14}
mkdir -p backups
file="backups/resto-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U resto -d resto -Fc > "$file.partial"
mv "$file.partial" "$file"
docker compose exec -T db pg_restore --list < "$file" > /dev/null  # fails loudly if the dump is unreadable
find backups -name 'resto-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $file ($(du -h "$file" | cut -f1))"
