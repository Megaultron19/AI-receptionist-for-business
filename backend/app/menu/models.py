from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_hi: Mapped[str] = mapped_column(String(80), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Addon(Base):
    __tablename__ = "menu_addons"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("menu_addon_groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    price_paise: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class AddonGroup(Base):
    """E.g. 'Extras' (choose up to 3) or 'Spice level' (choose exactly 1)."""
    __tablename__ = "menu_addon_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    addons: Mapped[list[Addon]] = relationship(lazy="selectin", order_by=Addon.sort, cascade="all, delete-orphan")


class ItemVariant(Base):
    """Portion sizes / variants with their own full price (Half / Full, Regular / Large)."""
    __tablename__ = "menu_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    price_paise: Mapped[int] = mapped_column(Integer)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("menu_categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_hi: Mapped[str] = mapped_column(String(120), default="")
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    price_paise: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str] = mapped_column(String(500), default="")
    dietary: Mapped[list[str]] = mapped_column(JSON, default=list)
    allergens: Mapped[str] = mapped_column(String(300), default="")
    spice_level: Mapped[str] = mapped_column(String(20), default="")
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=10)
    tax_rate_bp: Mapped[int | None] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped[MenuCategory] = relationship(lazy="joined")
    variants: Mapped[list[ItemVariant]] = relationship(lazy="selectin", order_by=ItemVariant.sort, cascade="all, delete-orphan")
    addon_groups: Mapped[list[AddonGroup]] = relationship(lazy="selectin", order_by=AddonGroup.sort, cascade="all, delete-orphan")
