import os
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import config


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    if url is None:
        os.makedirs(config().data_dir, exist_ok=True)
        url = f"sqlite:///{os.path.join(config().data_dir, 'restaurant.db')}"
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def on_connect(conn, _):
        conn.isolation_level = None
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


engine = make_engine()
Session = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with Session() as db:
        yield db


def now() -> datetime:
    return datetime.now(config().tz).replace(tzinfo=None, microsecond=0)
