import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import DomainError, NotFound
from ..db import get_db
from . import flow
from .providers import PROVIDERS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


async def _verified(request: Request, provider: str):
    p = PROVIDERS.get(provider)
    if not p:
        raise NotFound("Voice provider")
    params = {k: str(v) for k, v in (await request.form()).items()}
    url = get_settings().public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if not p.verify(url, params, request.headers):
        raise DomainError("Bad signature", "bad_signature", 403)
    return p, p.event(params)


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


@router.post("/{provider}/answer")
async def answer(provider: str, request: Request, db: Session = Depends(get_db)):
    p, ev = await _verified(request, provider)
    out = await run_in_threadpool(flow.incoming, db, p, ev)
    db.commit()
    return _xml(out)


@router.post("/{provider}/turn")
async def turn(provider: str, request: Request, n: int = 0, db: Session = Depends(get_db)):
    p, ev = await _verified(request, provider)
    try:
        out = await run_in_threadpool(flow.turn, db, p, ev, n)
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("voice turn failed")
        db.rollback()
        out = p.hangup("Sorry, something went wrong on our side. Please call again in a moment.", "en-IN")
    return _xml(out)


@router.post("/{provider}/dial-result")
async def dial_result(provider: str, request: Request, db: Session = Depends(get_db)):
    p, ev = await _verified(request, provider)
    out = await run_in_threadpool(flow.dial_result, db, p, ev)
    db.commit()
    return _xml(out)


@router.post("/{provider}/status")
async def status(provider: str, request: Request, db: Session = Depends(get_db)):
    p, ev = await _verified(request, provider)
    await run_in_threadpool(flow.status, db, p, ev)
    db.commit()
    return {"ok": True}
