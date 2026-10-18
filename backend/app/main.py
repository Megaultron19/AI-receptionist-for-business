import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import auth, checkin, menu, messaging, orders, payments, phone, razorpay, reservations, restaurant, tables
from .config import config
from .db import engine, migrate

migrate(engine)


@asynccontextmanager
async def lifespan(_):
    stop = threading.Event()
    if razorpay.enabled():
        payments.start_checker(stop)
    yield
    stop.set()


app = FastAPI(title="Restaurant Receptionist", docs_url=None, redoc_url=None, lifespan=lifespan)
for module in (auth, menu, tables, reservations, orders, restaurant, messaging, checkin, payments, phone):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(config().dashboard_dir):
    app.mount("/", StaticFiles(directory=config().dashboard_dir, html=True), name="dashboard")
