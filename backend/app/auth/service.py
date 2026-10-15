import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.errors import DomainError
from ..db import utcnow
from .models import StaffSession, StaffUser
from .permissions import ROLES

SCRYPT = dict(n=2**14, r=8, p=1)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(password.encode(), salt=salt, **SCRYPT).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


def validate_new_user(name: str, email: str, password: str | None, role: str) -> None:
    if not name.strip() or "@" not in email:
        raise DomainError("Name and a valid email are required.")
    if role not in ROLES:
        raise DomainError(f"Role must be one of {', '.join(ROLES)}.")
    if password is not None and len(password) < 10:
        raise DomainError("Password must be at least 10 characters.")


def create_user(db: Session, name: str, email: str, password: str, role: str) -> StaffUser:
    validate_new_user(name, email, password, role)
    email = email.strip().lower()
    if db.scalar(select(StaffUser).where(StaffUser.email == email)):
        raise DomainError("A staff account with that email already exists.", "conflict", 409)
    user = StaffUser(name=name.strip(), email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(db: Session, email: str, password: str, ip: str | None) -> tuple[StaffUser, str]:
    user = db.scalar(select(StaffUser).where(StaffUser.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user else hash_password("x" * 12))
    if not user or not ok or not user.active:
        raise DomainError("Wrong email or password.", "unauthorized", 401)
    token = secrets.token_urlsafe(32)
    db.add(StaffSession(token_hash=token_hash(token), user_id=user.id, ip=ip,
                        expires_at=utcnow() + timedelta(days=get_settings().session_days)))
    user.last_login_at = utcnow()
    return user, token


def session_user(db: Session, token: str) -> StaffUser | None:
    s = db.scalar(select(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    if not s or s.revoked_at or s.expires_at < utcnow() or not s.user.active:
        return None
    return s.user


def logout(db: Session, token: str) -> None:
    s = db.scalar(select(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    if s and not s.revoked_at:
        s.revoked_at = utcnow()


def revoke_all(db: Session, user_id: int) -> None:
    for s in db.scalars(select(StaffSession).where(StaffSession.user_id == user_id, StaffSession.revoked_at.is_(None))):
        s.revoked_at = utcnow()
