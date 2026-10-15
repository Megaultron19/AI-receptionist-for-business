import logging
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (registers all tables)
from . import registry  # noqa: F401  (registers job handlers)
from .auth.api import router as auth_router
from .config import get_settings
from .core.errors import DomainError
from .core.logging import request_id, setup_logging
from .core.models import WorkerHeartbeat
from .db import get_db, utcnow
from .reservations.api import router as reservations_router
from .restaurant.api import router as restaurant_router
from .tables.api import router as tables_router

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")

if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, send_default_pii=False, traces_sample_rate=0.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production and len(settings.secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be set to a random string of at least 32 characters in production")
    yield


app = FastAPI(title="AI Restaurant Receptionist", lifespan=lifespan,
              docs_url=None if settings.is_production else "/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id.set(rid[:64])
    try:
        response = await call_next(request)
    finally:
        request_id.reset(token)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError):
    return JSONResponse({"error": exc.code, "detail": exc.message}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    msgs = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse({"error": "validation", "detail": "; ".join(msgs)}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"error": "server_error", "detail": "Something went wrong. It has been logged."}, status_code=500)


for router in (auth_router, restaurant_router, tables_router, reservations_router):
    app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    """Ready = database reachable, schema migrated, background worker alive."""
    db.execute(text("select 1"))
    checks = {"database": True}
    try:
        checks["migrations"] = db.execute(text("select version_num from alembic_version")).scalar() is not None
    except Exception:  # noqa: BLE001
        db.rollback()
        checks["migrations"] = False
    beat = db.scalar(select(WorkerHeartbeat.beat_at).order_by(WorkerHeartbeat.beat_at.desc()).limit(1))
    checks["worker"] = bool(beat and utcnow() - beat < timedelta(minutes=2))
    ok = all(checks.values())
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)
