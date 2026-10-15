from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Table, text
from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow

combination_tables = Table(
    "combination_tables", Base.metadata,
    Column("combination_id", ForeignKey("table_combinations.id", ondelete="CASCADE"), primary_key=True),
    Column("table_id", ForeignKey("dining_tables.id", ondelete="CASCADE"), primary_key=True),
)


class DiningTable(Base):
    __tablename__ = "dining_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(60), default="")
    area: Mapped[str] = mapped_column(String(40), default="")
    capacity: Mapped[int] = mapped_column(Integer)
    min_capacity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("capacity >= 1 AND min_capacity >= 1 AND min_capacity <= capacity", name="capacity"),)


class TableCombination(Base):
    """Tables that may be pushed together for a larger party."""
    __tablename__ = "table_combinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    capacity: Mapped[int] = mapped_column(Integer)
    min_capacity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    tables: Mapped[list[DiningTable]] = relationship(secondary=combination_tables, lazy="selectin", order_by=DiningTable.sort)


class TableBlock(Base):
    """Staff-blocked period for a table (maintenance, private event, walk-in hold)."""
    __tablename__ = "table_blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    reason: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TableAllocation(Base):
    """The single source of truth for who holds a table when. The exclusion constraint makes it
    impossible - at the database level, across all channels and processes - for two active
    allocations (reservations or blocks) to overlap on the same table."""
    __tablename__ = "table_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id", ondelete="RESTRICT"), index=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), index=True)
    block_id: Mapped[int | None] = mapped_column(ForeignKey("table_blocks.id", ondelete="CASCADE"), index=True)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        ExcludeConstraint(("table_id", "="), ("period", "&&"), where=text("active"), using="gist",
                          name="no_overlapping_allocations"),
        CheckConstraint("(reservation_id IS NULL) <> (block_id IS NULL)", name="one_owner"),
    )
