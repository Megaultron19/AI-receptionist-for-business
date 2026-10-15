#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
dump=${1:?usage: deploy/restore.sh <backup.dump>}
read -r -p "This replaces ALL data of project '$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')' with $dump. Type RESTORE to continue: " ok
[ "$ok" = "RESTORE" ] || { echo "aborted"; exit 1; }
docker compose stop api worker
docker compose exec -T db psql -U resto -d postgres -c "DROP DATABASE IF EXISTS resto WITH (FORCE);" -c "CREATE DATABASE resto OWNER resto;"
docker compose exec -T db pg_restore -U resto -d resto --no-owner < "$dump"
docker compose run --rm migrate
docker compose start api worker
echo "restored $dump"
