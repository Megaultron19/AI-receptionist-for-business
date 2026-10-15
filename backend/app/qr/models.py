from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, utcnow


class QrToken(Base):
    """A QR code points at /q/<token>. Only the SHA-256 of the token is stored, so a database leak can't
    be turned into valid QR codes; the code itself carries no personal or payment data."""
    __tablename__ = "qr_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(12))
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    first_scanned_at: Mapped[datetime | None]
    scan_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class QrScan(Base):
    __tablename__ = "qr_scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    qr_id: Mapped[int | None] = mapped_column(ForeignKey("qr_tokens.id", ondelete="CASCADE"), index=True)
    scanned_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    staff_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(12))
    result: Mapped[str] = mapped_column(String(24))
