import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, engine
from app.main import app


def test_migrations_match_models():
    """The migrated schema (built by conftest via `alembic upgrade head`) has no drift from the models."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], diff
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "0001"
        assert conn.execute(text("select 1 from pg_extension where extname = 'btree_gist'")).scalar() == 1


def test_health_and_readiness(db):
    c = TestClient(app)
    assert c.get("/healthz").json() == {"ok": True}
    r = c.get("/readyz")
    assert r.status_code == 503 and r.json()["checks"] == {"database": True, "migrations": True, "worker": False}
    from app.core.jobs import heartbeat
    heartbeat("worker@test")
    assert c.get("/readyz").status_code == 200
    assert c.get("/healthz").headers["X-Request-ID"]


def test_env_template_lists_every_setting():
    from app.config import Settings
    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
    keys = {line.split("=")[0].strip().lstrip("# ") for line in open(path) if "=" in line}
    missing = {f.upper() for f in Settings.model_fields} - keys
    assert not missing, f".env.example is missing {sorted(missing)}"
