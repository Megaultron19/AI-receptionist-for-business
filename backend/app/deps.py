"""Request dependencies: DB session, authenticated staff user, permission checks, CSRF."""
import hmac

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .auth.models import StaffUser
from .auth.permissions import can
from .auth.service import session_user
from .core.errors import DomainError
from .db import get_db

SESSION_COOKIE = "rr_session"
CSRF_COOKIE = "rr_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> StaffUser:
    token = request.cookies.get(SESSION_COOKIE)
    user = session_user(db, token) if token else None
    if not user:
        raise DomainError("Please log in.", "unauthorized", 401)
    if request.method not in SAFE_METHODS:
        # Double-submit CSRF token: a cross-site page can't read our cookie to echo it in the header.
        cookie, header = request.cookies.get(CSRF_COOKIE, ""), request.headers.get("X-CSRF-Token", "")
        if not cookie or not hmac.compare_digest(cookie, header):
            raise DomainError("Missing or invalid CSRF token. Reload the page.", "csrf", 403)
    request.state.user = user
    return user


def require(permission: str):
    def dep(user: StaffUser = Depends(current_user)) -> StaffUser:
        if not can(user.role, permission):
            raise DomainError("You don't have permission to do that.", "forbidden", 403)
        return user
    return dep


def actor(user: StaffUser) -> tuple[str, int]:
    return ("staff", user.id)
