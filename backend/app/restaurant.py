import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .auth import current_user, owner_only
from .db import get_db
from .reservations import DAYS, restaurant

router = APIRouter(prefix="/api/restaurant")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FIELDS = ("name", "phone", "address", "about", "hours", "slot_minutes", "dining_minutes", "max_guests", "advance_days", "prep_target_minutes")


class RestaurantIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field("", max_length=20)
    address: str = Field("", max_length=500)
    about: str = Field("", max_length=5000)
    hours: dict[str, list[list[str]]]
    slot_minutes: int = Field(ge=10, le=120)
    dining_minutes: int = Field(ge=15, le=300)
    max_guests: int = Field(ge=1, le=100)
    advance_days: int = Field(ge=0, le=365)
    prep_target_minutes: int = Field(ge=1, le=120)

    @field_validator("hours")
    @classmethod
    def valid_hours(cls, hours):
        for day, windows in hours.items():
            if day not in DAYS:
                raise ValueError(f"Unknown day {day}")
            for window in windows:
                if len(window) != 2 or not all(HHMM.match(t) for t in window) or window[0] == window[1]:
                    raise ValueError(f"Hours for {day} must look like 12:00 to 15:30")
        return {day: hours.get(day, []) for day in DAYS}


@router.get("")
def read(db: Session = Depends(get_db), _=Depends(current_user)):
    r = restaurant(db)
    db.commit()
    return {f: getattr(r, f) for f in FIELDS}


@router.put("")
def update(body: RestaurantIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    r = restaurant(db)
    for key, value in body.model_dump().items():
        setattr(r, key, value)
    db.commit()
    return {f: getattr(r, f) for f in FIELDS}
