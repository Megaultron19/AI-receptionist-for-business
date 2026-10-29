import os
import sqlite3
from datetime import datetime

from sqlalchemy import create_engine, event, inspect, literal
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


def migrate(engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        existing = inspect(conn)
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                sql = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}"
                default = column.default.arg if column.default is not None and not callable(column.default.arg) else None
                if default is not None:
                    sql += " DEFAULT " + str(literal(default).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))
                conn.exec_driver_sql(sql)


engine = make_engine()
Session = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with Session() as db:
        yield db


def now() -> datetime:
    return datetime.now(config().tz).replace(tzinfo=None, microsecond=0)


def backup_database() -> None:
    folder = os.path.join(config().data_dir, "backups")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"restaurant-{now():%Y-%m-%d}.db")
    if not os.path.exists(target):
        source, copy = sqlite3.connect(os.path.join(config().data_dir, "restaurant.db")), sqlite3.connect(target)
        with copy:
            source.backup(copy)
        source.close()
        copy.close()
    for old in sorted(f for f in os.listdir(folder) if f.startswith("restaurant-"))[:-config().backups_to_keep]:
        os.remove(os.path.join(folder, old))
