from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core.errors import Conflict, DomainError, NotFound
from ..core.events import audit
from ..db import get_db
from ..deps import actor, require
from ..reservations.models import Reservation
from ..core.jobs import enqueue
from ..restaurant.service import day_bounds, get_restaurant, parse_time, tz
from .models import DiningTable, TableAllocation, TableBlock, TableCombination

router = APIRouter(prefix="/api/tables", tags=["tables"])


class TableIn(BaseModel):
    code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field("", max_length=60)
    area: str = Field("", max_length=40)
    capacity: int = Field(ge=1, le=100)
    min_capacity: int = Field(1, ge=1, le=100)
    active: bool = True
    sort: int = 0


class ComboIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    table_ids: list[int] = Field(min_length=2)
    capacity: int | None = Field(None, ge=1, le=200)
    min_capacity: int = Field(1, ge=1)
    active: bool = True


class BlockIn(BaseModel):
    table_ids: list[int] = Field(min_length=1)
    starts_at: str
    ends_at: str
    reason: str = Field("", max_length=200)


def table_out(t: DiningTable) -> dict:
    return {"id": t.id, "code": t.code, "name": t.name, "area": t.area, "capacity": t.capacity,
            "min_capacity": t.min_capacity, "active": t.active, "sort": t.sort}


def combo_out(c: TableCombination) -> dict:
    return {"id": c.id, "name": c.name, "capacity": c.capacity, "min_capacity": c.min_capacity, "active": c.active,
            "table_ids": [t.id for t in c.tables], "tables": [t.code for t in c.tables]}


@router.get("")
def list_tables(db: Session = Depends(get_db), _: StaffUser = Depends(require("tables.view"))):
    return {"tables": [table_out(t) for t in db.scalars(select(DiningTable).order_by(DiningTable.sort, DiningTable.code))],
            "combinations": [combo_out(c) for c in db.scalars(select(TableCombination).order_by(TableCombination.name))]}


@router.post("")
def create_table(body: TableIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.manage"))):
    if body.min_capacity > body.capacity:
        raise DomainError("Minimum guests can't exceed capacity.")
    t = DiningTable(**body.model_dump())
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        raise Conflict(f"Table code {body.code} already exists.")
    audit(db, "table.created", "table", t.code, actor=actor(user), capacity=t.capacity)
    db.commit()
    return table_out(t)


@router.put("/{table_id}")
def update_table(table_id: int, body: TableIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.manage"))):
    t = db.get(DiningTable, table_id)
    if not t:
        raise NotFound("Table")
    if body.min_capacity > body.capacity:
        raise DomainError("Minimum guests can't exceed capacity.")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    try:
        db.flush()
    except IntegrityError:
        raise Conflict(f"Table code {body.code} already exists.")
    audit(db, "table.updated", "table", t.code, actor=actor(user), **body.model_dump())
    db.commit()
    return table_out(t)


def _combo_tables(db: Session, ids: list[int]) -> list[DiningTable]:
    tables = list(db.scalars(select(DiningTable).where(DiningTable.id.in_(ids))))
    if len(tables) != len(set(ids)):
        raise DomainError("Unknown table in combination.")
    return tables


@router.post("/combinations")
def create_combo(body: ComboIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.manage"))):
    tables = _combo_tables(db, body.table_ids)
    c = TableCombination(name=body.name, capacity=body.capacity or sum(t.capacity for t in tables),
                         min_capacity=body.min_capacity, active=body.active, tables=tables)
    db.add(c)
    db.flush()
    audit(db, "table_combination.created", "table_combination", c.id, actor=actor(user), tables=[t.code for t in tables])
    db.commit()
    return combo_out(c)


@router.put("/combinations/{combo_id}")
def update_combo(combo_id: int, body: ComboIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.manage"))):
    c = db.get(TableCombination, combo_id)
    if not c:
        raise NotFound("Combination")
    tables = _combo_tables(db, body.table_ids)
    c.name, c.tables, c.active, c.min_capacity = body.name, tables, body.active, body.min_capacity
    c.capacity = body.capacity or sum(t.capacity for t in tables)
    audit(db, "table_combination.updated", "table_combination", c.id, actor=actor(user))
    db.commit()
    return combo_out(c)


@router.delete("/combinations/{combo_id}")
def delete_combo(combo_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.manage"))):
    c = db.get(TableCombination, combo_id)
    if not c:
        raise NotFound("Combination")
    audit(db, "table_combination.deleted", "table_combination", c.id, actor=actor(user), name=c.name)
    db.delete(c)
    db.commit()
    return {"ok": True}


def block_out(b: TableBlock) -> dict:
    return {"id": b.id, "table_id": b.table_id, "starts_at": b.starts_at, "ends_at": b.ends_at, "reason": b.reason, "active": b.active}


@router.post("/blocks")
def create_block(body: BlockIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.block"))):
    r = get_restaurant(db)
    start, end = parse_time(r, body.starts_at), parse_time(r, body.ends_at)
    if end <= start or end - start > timedelta(days=60):
        raise DomainError("Block must end after it starts (max 60 days).")
    blocks = []
    try:
        with db.begin_nested():
            for tid in body.table_ids:
                if not db.get(DiningTable, tid):
                    raise NotFound("Table")
                b = TableBlock(table_id=tid, starts_at=start, ends_at=end, reason=body.reason, created_by=user.id)
                db.add(b)
                db.flush()
                db.add(TableAllocation(table_id=tid, block_id=b.id, period=Range(start, end, bounds="[)"), active=True))
                db.flush()
                blocks.append(b)
    except IntegrityError as e:
        if getattr(e.orig, "sqlstate", None) == "23P01":
            raise Conflict("That table already has a booking or block in this period. Move or cancel it first.")
        raise
    for b in blocks:
        audit(db, "table.blocked", "table", b.table_id, actor=actor(user), start=start.isoformat(), end=end.isoformat(), reason=b.reason)
    db.commit()
    return [block_out(b) for b in blocks]


@router.delete("/blocks/{block_id}")
def remove_block(block_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("tables.block"))):
    b = db.get(TableBlock, block_id)
    if not b or not b.active:
        raise NotFound("Block")
    b.active = False
    for a in db.scalars(select(TableAllocation).where(TableAllocation.block_id == b.id)):
        a.active = False
    audit(db, "table.unblocked", "table", b.table_id, actor=actor(user), block_id=b.id)
    day = b.starts_at.astimezone(tz(get_restaurant(db))).date()
    enqueue(db, "waitlist.process", {"day": day.isoformat()}, dedupe_key=f"waitlist:{day}:unblock:{b.id}")
    db.commit()
    return {"ok": True}


@router.get("/timeline")
def timeline(day: date, db: Session = Depends(get_db), _: StaffUser = Depends(require("tables.view"))):
    """Everything holding each table on `day` (local): reservations and blocks."""
    r = get_restaurant(db)
    start, end = day_bounds(r, day)
    end += timedelta(hours=6)
    window = TableAllocation.active, TableAllocation.period.overlaps(Range(start, end, bounds="[)"))
    items: dict[int, list] = {}
    for a, res in db.execute(select(TableAllocation, Reservation).join(Reservation, TableAllocation.reservation_id == Reservation.id).where(*window)):
        items.setdefault(a.table_id, []).append({
            "from": a.period.lower, "to": a.period.upper, "type": "reservation", "ref": res.ref, "status": res.status,
            "party": res.party_size, "name": res.customer.name, "starts_at": res.starts_at, "ends_at": res.ends_at})
    for a, blk in db.execute(select(TableAllocation, TableBlock).join(TableBlock, TableAllocation.block_id == TableBlock.id).where(*window)):
        items.setdefault(a.table_id, []).append({"from": a.period.lower, "to": a.period.upper, "type": "block",
                                                 "block_id": blk.id, "reason": blk.reason})
    tables = db.scalars(select(DiningTable).where(DiningTable.active).order_by(DiningTable.sort, DiningTable.code))
    return [{**table_out(t), "items": sorted(items.get(t.id, []), key=lambda i: i["from"])} for t in tables]
