from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.models import StaffUser
from ..core import ratelimit
from ..core.errors import NotFound
from ..db import get_db
from ..deps import require
from ..restaurant.service import get_restaurant, tz
from . import service

router = APIRouter(tags=["qr"])


class ScanIn(BaseModel):
    code: str = Field(min_length=10, max_length=500)


@router.post("/api/checkin/lookup")
def lookup(body: ScanIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("checkin"))):
    out = service.describe(db, body.code, staff_id=user.id, action="lookup")
    db.commit()
    return out


@router.post("/api/checkin/confirm")
def confirm(body: ScanIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("checkin"))):
    out = service.describe(db, body.code, staff_id=user.id, action="checkin")
    db.commit()
    return out


@router.get("/q/{token}.png")
def qr_png(token: str, request: Request, db: Session = Depends(get_db)):
    ratelimit.check(f"qr:{request.client.host if request.client else '?'}", 60, 60)
    if not service.public_view(db, token):
        raise NotFound("QR code")
    return Response(service.png(token), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/q/{token}", response_class=HTMLResponse)
def qr_page(token: str, request: Request, db: Session = Depends(get_db)):
    """Fallback when the image can't be delivered on WhatsApp: the guest opens this link and shows it."""
    ratelimit.check(f"qr:{request.client.host if request.client else '?'}", 60, 60)
    view = service.public_view(db, token)
    r = get_restaurant(db)
    if not view:
        return HTMLResponse("<h2>This QR code is no longer valid.</h2>", status_code=404)
    zone = tz(r)
    if view["kind"] == "reservation":
        detail = f"Booking {escape(view['ref'])} · {view['party_size']} guests · {view['starts_at'].astimezone(zone):%a %d %b, %I:%M %p}"
    else:
        eta = view["estimated_ready_at"]
        detail = f"Order {escape(view['ref'])}" + (f" · ready around {eta.astimezone(zone):%I:%M %p}" if eta else "")
    return HTMLResponse(f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>{escape(r.name)}</title><body style="font-family:system-ui;text-align:center;padding:24px">
<h2>{escape(r.name)}</h2><p>{detail}</p><p>Status: {escape(view['status'].replace('_', ' '))}</p>
<img src="/q/{escape(token)}.png" alt="QR code" style="width:260px;max-width:90%"><p>Show this code at the restaurant.</p>""")
