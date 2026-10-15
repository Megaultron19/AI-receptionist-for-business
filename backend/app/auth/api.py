import secrets

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import ratelimit
from ..core.errors import DomainError, NotFound
from ..core.events import audit
from ..db import get_db
from ..deps import CSRF_COOKIE, SESSION_COOKIE, actor, current_user, require
from . import service
from .models import StaffUser
from .permissions import PERMISSIONS

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: StaffUser) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.active,
            "last_login_at": u.last_login_at, "permissions": sorted(PERMISSIONS.get(u.role, []))}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    ratelimit.check(f"login:{ip}", 10, 300)
    ratelimit.check(f"login:{body.email.lower()}", 5, 300)
    try:
        user, token = service.login(db, body.email, body.password, ip)
    except DomainError:
        audit(db, "auth.login_failed", "staff_user", None, email=body.email.lower()[:254], ip=ip)
        db.commit()
        raise
    audit(db, "auth.login", "staff_user", user.id, actor=("staff", user.id), ip=ip)
    db.commit()
    secure = get_settings().is_production
    max_age = get_settings().session_days * 86400
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=secure, samesite="lax", max_age=max_age, path="/")
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, secure=secure, samesite="lax",
                        max_age=max_age, path="/")
    return user_out(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: StaffUser = Depends(current_user)):
    service.logout(db, request.cookies.get(SESSION_COOKIE, ""))
    audit(db, "auth.logout", "staff_user", user.id, actor=actor(user))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: StaffUser = Depends(current_user)):
    return user_out(user)


class StaffIn(BaseModel):
    name: str
    email: str
    password: str
    role: str


class StaffPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None


@router.get("/staff")
def list_staff(db: Session = Depends(get_db), _: StaffUser = Depends(require("staff.manage"))):
    return [user_out(u) for u in db.scalars(select(StaffUser).order_by(StaffUser.id))]


@router.post("/staff")
def create_staff(body: StaffIn, db: Session = Depends(get_db), user: StaffUser = Depends(require("staff.manage"))):
    u = service.create_user(db, body.name, body.email, body.password, body.role)
    audit(db, "staff.created", "staff_user", u.id, actor=actor(user), role=u.role, email=u.email)
    db.commit()
    return user_out(u)


@router.patch("/staff/{user_id}")
def update_staff(user_id: int, body: StaffPatch, db: Session = Depends(get_db),
                 user: StaffUser = Depends(require("staff.manage"))):
    u = db.get(StaffUser, user_id)
    if not u:
        raise NotFound("Staff user")
    changes = body.model_dump(exclude_none=True)
    if "role" in changes or "active" in changes:
        if u.id == user.id:
            raise DomainError("You can't change your own role or deactivate yourself.")
    service.validate_new_user(changes.get("name", u.name), u.email, changes.get("password"), changes.get("role", u.role))
    if "name" in changes:
        u.name = changes["name"].strip()
    if "role" in changes:
        u.role = changes["role"]
    if "active" in changes:
        u.active = changes["active"]
    if "password" in changes:
        u.password_hash = service.hash_password(changes["password"])
    if changes.keys() & {"role", "active", "password"}:
        service.revoke_all(db, u.id)
    audit(db, "staff.updated", "staff_user", u.id, actor=actor(user), fields=sorted(k for k in changes if k != "password"),
          password_reset="password" in changes)
    db.commit()
    return user_out(u)
