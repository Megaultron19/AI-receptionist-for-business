import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import auth, checkin, menu, messaging, reservations, restaurant, tables
from .config import config
from .db import Base, engine

Base.metadata.create_all(engine)

app = FastAPI(title="Restaurant Receptionist", docs_url=None, redoc_url=None)
for module in (auth, menu, tables, reservations, restaurant, messaging, checkin):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(config().dashboard_dir):
    app.mount("/", StaticFiles(directory=config().dashboard_dir, html=True), name="dashboard")
