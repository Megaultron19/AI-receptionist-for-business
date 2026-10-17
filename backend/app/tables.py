from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, owner_only
from .db import get_db
from .models import Block, DiningTable, Reservation

router = APIRouter(prefix="/api")


class TableIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    seats: int = Field(ge=1, le=50)
    available: bool = True


class BlockIn(BaseModel):
    table_id: int | None = None
    starts_at: datetime
    ends_at: datetime
    reason: str = Field("", max_length=200)


def table_out(t: DiningTable) -> dict:
    return {"id": t.id, "name": t.name, "seats": t.seats, "available": t.available}


def block_out(b: Block) -> dict:
    return {"id": b.id, "table_id": b.table_id, "starts_at": b.starts_at, "ends_at": b.ends_at, "reason": b.reason}


@router.get("/tables")
def list_tables(db: Session = Depends(get_db), _=Depends(current_user)):
    return [table_out(t) for t in db.scalars(select(DiningTable).order_by(DiningTable.name))]


@router.post("/tables")
def add_table(body: TableIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    table = DiningTable(**body.model_dump())
    db.add(table)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(400, f"A table named {body.name} already exists")
    return table_out(table)


@router.put("/tables/{table_id}")
def edit_table(table_id: int, body: TableIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    table = db.get(DiningTable, table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    for key, value in body.model_dump().items():
        setattr(table, key, value)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(400, f"A table named {body.name} already exists")
    return table_out(table)


@router.post("/tables/{table_id}/available")
def set_available(table_id: int, available: bool, db: Session = Depends(get_db), _=Depends(current_user)):
    table = db.get(DiningTable, table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    table.available = available
    db.commit()
    return table_out(table)


@router.delete("/tables/{table_id}")
def delete_table(table_id: int, db: Session = Depends(get_db), _=Depends(owner_only)):
    table = db.get(DiningTable, table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    if db.scalar(select(Reservation.id).where(Reservation.table_id == table_id).limit(1)):
        raise HTTPException(400, "This table has bookings. Mark it unavailable instead.")
    db.delete(table)
    db.commit()
    return {"ok": True}


@router.get("/blocks")
def list_blocks(db: Session = Depends(get_db), _=Depends(current_user)):
    return [block_out(b) for b in db.scalars(select(Block).order_by(Block.starts_at))]


@router.post("/blocks")
def add_block(body: BlockIn, db: Session = Depends(get_db), _=Depends(current_user)):
    if body.ends_at <= body.starts_at:
        raise HTTPException(400, "Block must end after it starts")
    if body.table_id is not None and not db.get(DiningTable, body.table_id):
        raise HTTPException(404, "Table not found")
    block = Block(**body.model_dump())
    db.add(block)
    db.commit()
    return block_out(block)


@router.delete("/blocks/{block_id}")
def delete_block(block_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    block = db.get(Block, block_id)
    if not block:
        raise HTTPException(404, "Block not found")
    db.delete(block)
    db.commit()
    return {"ok": True}
