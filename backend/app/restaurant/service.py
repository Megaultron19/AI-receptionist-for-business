from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import RestaurantSettings, SpecialDay
from .schemas import DAYS


def get_restaurant(db: Session, *, for_update: bool = False) -> RestaurantSettings:
    q = select(RestaurantSettings).where(RestaurantSettings.id == 1)
    if for_update:
        q = q.with_for_update()
    r = db.scalar(q)
    if r is None:
        r = RestaurantSettings(id=1)
        db.add(r)
        db.flush()
    return r


def tz(r: RestaurantSettings) -> ZoneInfo:
    return ZoneInfo(r.timezone)


def local_now(r: RestaurantSettings) -> datetime:
    return datetime.now(tz(r))


def open_intervals(db: Session, r: RestaurantSettings, day: date) -> list[tuple[datetime, datetime]]:
    """Opening intervals that START on `day` (local), as aware datetimes. End <= start means past midnight."""
    special = db.scalar(select(SpecialDay).where(SpecialDay.day == day))
    if special:
        raw = [] if special.closed else special.intervals
    else:
        raw = r.opening_hours.get(DAYS[day.weekday()], [])
    zone, out = tz(r), []
    for start, end in raw:
        s = datetime.combine(day, time.fromisoformat(start), zone)
        e = datetime.combine(day, time.fromisoformat(end), zone)
        if e <= s:
            e += timedelta(days=1)
        out.append((s, e))
    return out


def is_open_between(db: Session, r: RestaurantSettings, start: datetime, end: datetime) -> bool:
    """True if [start, end] fits entirely inside one opening interval (checks the previous day for
    intervals that run past midnight)."""
    local = start.astimezone(tz(r))
    for d in (local.date(), local.date() - timedelta(days=1)):
        if any(s <= start and end <= e for s, e in open_intervals(db, r, d)):
            return True
    return False


def duration_for(r: RestaurantSettings, party: int) -> int:
    minutes = r.default_duration_minutes
    for rule in sorted(r.duration_rules or [], key=lambda x: x["min_party"]):
        if party >= rule["min_party"]:
            minutes = rule["minutes"]
    return minutes


def parse_time(r: RestaurantSettings, value: str | datetime) -> datetime:
    """ISO datetime; naive values are read as restaurant-local time."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt.replace(tzinfo=tz(r)) if dt.tzinfo is None else dt


def day_bounds(r: RestaurantSettings, day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tz(r))
    return start, start + timedelta(days=1)
