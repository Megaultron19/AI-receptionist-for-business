#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP_DAYS=${KEEP_DAYS:-14}
mkdir -p backups
file="backups/resto-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U resto -d resto -Fc > "$file.partial"
mv "$file.partial" "$file"
docker compose exec -T db pg_restore --list < "$file" > /dev/null
find backups -name 'resto-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $file ($(du -h "$file" | cut -f1))"
