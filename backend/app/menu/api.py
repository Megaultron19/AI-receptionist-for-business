from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core.errors import DomainError, NotFound
from ..core.events import audit
from ..db import get_db
from ..deps import actor, require
from .models import Addon, AddonGroup, ItemVariant, MenuCategory, MenuItem

router = APIRouter(prefix="/api/menu", tags=["menu"])
DIETARY = {"veg", "non_veg", "egg", "vegan", "jain", "gluten_free", "contains_nuts", "dairy_free"}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_hi: str = Field("", max_length=80)
    sort: int = 0
    active: bool = True


class VariantIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price_paise: int = Field(ge=0, le=10_000_000)
    available: bool = True


class AddonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price_paise: int = Field(0, ge=0, le=10_000_000)
    available: bool = True


class AddonGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    min_select: int = Field(0, ge=0, le=20)
    max_select: int = Field(1, ge=1, le=20)
    addons: list[AddonIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _range(self):
        if self.min_select > self.max_select or self.min_select > len(self.addons):
            raise ValueError("min_select must be <= max_select and <= number of add-ons")
        return self


class ItemIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=120)
    name_hi: str = Field("", max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field("", max_length=1000)
    price_paise: int = Field(0, ge=0, le=10_000_000)
    image_url: str = Field("", max_length=500, pattern=r"^(https://.*)?$")
    dietary: list[str] = []
    allergens: str = Field("", max_length=300)
    spice_level: str = Field("", max_length=20)
    available: bool = True
    prep_minutes: int = Field(10, ge=0, le=240)
    tax_rate_bp: int | None = Field(None, ge=0, le=5000)
    sort: int = 0
    variants: list[VariantIn] = []
    addon_groups: list[AddonGroupIn] = []

    @model_validator(mode="after")
    def _check(self):
        if bad := set(self.dietary) - DIETARY:
            raise ValueError(f"unknown dietary tags {sorted(bad)}; use {sorted(DIETARY)}")
        if not self.variants and self.price_paise <= 0:
            raise ValueError("give a price, or at least one variant with a price")
        if len({v.name.lower() for v in self.variants}) != len(self.variants):
            raise ValueError("variant names must be unique")
        return self


class AvailabilityIn(BaseModel):
    available: bool
    variant_id: int | None = None
    addon_id: int | None = None


def item_out(it: MenuItem) -> dict:
    return {
        "id": it.id, "category_id": it.category_id, "category": it.category.name, "name": it.name, "name_hi": it.name_hi,
        "aliases": it.aliases, "description": it.description, "price_paise": it.price_paise, "image_url": it.image_url,
        "dietary": it.dietary, "allergens": it.allergens, "spice_level": it.spice_level, "available": it.available,
        "prep_minutes": it.prep_minutes, "tax_rate_bp": it.tax_rate_bp, "sort": it.sort, "active": it.active,
        "variants": [{"id": v.id, "name": v.name, "price_paise": v.price_paise, "available": v.available} for v in it.variants],
        "addon_groups": [{"id": g.id, "name": g.name, "min_select": g.min_select, "max_select": g.max_select,
                          "addons": [{"id": a.id, "name": a.name, "price_paise": a.price_paise, "available": a.available}
                                     for a in g.addons]} for g in it.addon_groups],
    }


def cat_out(c: MenuCategory) -> dict:
    return {"id": c.id, "name": c.name, "name_hi": c.name_hi, "sort": c.sort, "active": c.active}


@router.get("")
def full_menu(db: Session = Depends(get_db), _: StaffUser = Depends(require("menu.view"))):
    cats = db.scalars(select(MenuCategory).order_by(MenuCategory.sort, MenuCategory.name)).all()
    items = db.scalars(select(MenuItem).where(MenuItem.active).order_by(MenuItem.sort, MenuItem.name)).all()
    return {"categories": [cat_out(c) for c in cats], "items": [item_out(i) for i in items]}


@router.post("/categories")
def create_category(body: CategoryIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("menu.manage"))):
    c = MenuCategory(**body.model_dump())
    db.add(c)
    db.flush()
    audit(db, "menu.category_created", "menu_category", c.id, actor=actor(user), name=c.name)
    db.commit()
    return cat_out(c)


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("menu.manage"))):
    c = db.get(MenuCategory, cat_id)
    if not c:
        raise NotFound("Category")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, "menu.category_updated", "menu_category", c.id, actor=actor(user))
    db.commit()
    return cat_out(c)


def _apply(it: MenuItem, body: ItemIn) -> None:
    data = body.model_dump(exclude={"variants", "addon_groups"})
    data["aliases"] = [a.strip() for a in data["aliases"] if a.strip()]
    for k, v in data.items():
        setattr(it, k, v)
    it.variants = [ItemVariant(sort=i, **v.model_dump()) for i, v in enumerate(body.variants)]
    it.addon_groups = [AddonGroup(sort=i, name=g.name, min_select=g.min_select, max_select=g.max_select,
                                  addons=[Addon(sort=j, **a.model_dump()) for j, a in enumerate(g.addons)])
                       for i, g in enumerate(body.addon_groups)]


@router.post("/items")
def create_item(body: ItemIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("menu.manage"))):
    if not db.get(MenuCategory, body.category_id):
        raise DomainError("Unknown category.")
    it = MenuItem()
    _apply(it, body)
    db.add(it)
    db.flush()
    audit(db, "menu.item_created", "menu_item", it.id, actor=actor(user), name=it.name, price=it.price_paise)
    db.commit()
    db.refresh(it)
    return item_out(it)


@router.put("/items/{item_id}")
def update_item(item_id: int, body: ItemIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("menu.manage"))):
    it = db.get(MenuItem, item_id)
    if not it or not it.active:
        raise NotFound("Menu item")
    if not db.get(MenuCategory, body.category_id):
        raise DomainError("Unknown category.")
    before = item_out(it)
    _apply(it, body)
    db.flush()
    db.refresh(it)
    after = item_out(it)
    audit(db, "menu.item_updated", "menu_item", it.id, actor=actor(user),
          changed=sorted(k for k in after if k not in ("variants", "addon_groups") and before.get(k) != after.get(k)),
          price_before=before["price_paise"], price_after=after["price_paise"])
    db.commit()
    return after


@router.post("/items/{item_id}/availability")
def set_availability(item_id: int, body: AvailabilityIn, db: Session = Depends(get_db),
                     user: StaffUser = Depends(require("menu.availability"))):
    it = db.get(MenuItem, item_id)
    if not it or not it.active:
        raise NotFound("Menu item")
    target = it
    if body.variant_id:
        target = next((v for v in it.variants if v.id == body.variant_id), None)
    elif body.addon_id:
        target = next((a for g in it.addon_groups for a in g.addons if a.id == body.addon_id), None)
    if target is None:
        raise NotFound("Variant or add-on")
    target.available = body.available
    audit(db, "menu.availability", "menu_item", it.id, actor=actor(user), available=body.available,
          variant_id=body.variant_id, addon_id=body.addon_id)
    db.commit()
    return item_out(it)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user: StaffUser = Depends(require("menu.manage"))):
    it = db.get(MenuItem, item_id)
    if not it or not it.active:
        raise NotFound("Menu item")
    it.active = False
    audit(db, "menu.item_deleted", "menu_item", it.id, actor=actor(user), name=it.name)
    db.commit()
    return {"ok": True}
