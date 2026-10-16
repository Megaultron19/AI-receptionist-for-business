from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user, owner_only
from .db import get_db
from .models import MenuItem

router = APIRouter(prefix="/api/menu")


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field("", max_length=60)
    description: str = Field("", max_length=500)
    price: int = Field(gt=0, description="Price in rupees")
    veg: bool = True
    available: bool = True
    prep_minutes: int = Field(10, ge=0, le=180)
    other_names: str = Field("", max_length=300)


def item_out(i: MenuItem) -> dict:
    return {c: getattr(i, c) for c in ("id", "name", "category", "description", "price", "veg", "available", "prep_minutes", "other_names")}


@router.get("")
def list_items(db: Session = Depends(get_db), _=Depends(current_user)):
    return [item_out(i) for i in db.scalars(select(MenuItem).order_by(MenuItem.category, MenuItem.name))]


@router.post("")
def add_item(body: ItemIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    item = MenuItem(**body.model_dump())
    db.add(item)
    db.commit()
    return item_out(item)


@router.put("/{item_id}")
def edit_item(item_id: int, body: ItemIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return item_out(item)


@router.post("/{item_id}/available")
def set_available(item_id: int, available: bool, db: Session = Depends(get_db), _=Depends(current_user)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    item.available = available
    db.commit()
    return item_out(item)


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), _=Depends(owner_only)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}
