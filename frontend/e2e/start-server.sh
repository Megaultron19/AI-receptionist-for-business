#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../backend"
PY=${PYTHON:-../.venv/bin/python}
export DATABASE_URL=${E2E_DATABASE_URL:-postgresql+psycopg://postgres@localhost:5432/resto_e2e}
export SECRET_KEY=e2e-secret-key-e2e-secret-key-e2e-secret PUBLIC_BASE_URL=http://localhost:8100 DASHBOARD_DIR=../frontend/out ENVIRONMENT=test
$PY - <<'PY'
import os
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"]
base, name = url.rsplit("/", 1)
with create_engine(base + "/postgres", isolation_level="AUTOCOMMIT").connect() as c:
    c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    c.execute(text(f'CREATE DATABASE "{name}"'))
PY
../.venv/bin/alembic upgrade head
$PY -m app.cli seed-demo
$PY -m app.cli create-owner --name "Owner" --email owner@e2e.test --password "e2e-owner-password"
$PY - <<'PY'
from app.auth.service import create_user
from app.db import SessionLocal
with SessionLocal() as db:
    create_user(db, "Kitchen", "kitchen@e2e.test", "e2e-kitchen-password", "staff")
    db.commit()
PY
exec $PY -m uvicorn app.main:app --port 8100 --log-level warning
