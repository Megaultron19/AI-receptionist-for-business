import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from . import auth, checkin, inbox, jobs, menu, messaging, orders, payments, phone, receptionist, reservations, restaurant, tables, users, waitlist
from .config import config
from .db import engine, migrate

migrate(engine)


@asynccontextmanager
async def lifespan(_):
    stop = threading.Event()
    jobs.start(stop)
    yield
    stop.set()
    receptionist.stop_tunnel()


app = FastAPI(title="Restaurant Receptionist", docs_url=None, redoc_url=None, lifespan=lifespan)
for module in (auth, menu, tables, reservations, orders, restaurant, messaging, checkin, payments, phone, inbox, waitlist, receptionist, users):
    app.include_router(module.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin"})
    return response


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(config().dashboard_dir):
    app.mount("/", StaticFiles(directory=config().dashboard_dir, html=True), name="dashboard")
