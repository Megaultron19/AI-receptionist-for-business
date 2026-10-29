import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, now
from .models import LoginSession, User

router = APIRouter(prefix="/api/auth")
COOKIE = "session"
ROLES = ("owner", "staff")
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
failed_logins: dict[str, list] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def check_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(":")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(candidate, digest)


def create_user(db: Session, username: str, password: str, role: str) -> User:
    if role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.scalar(select(User).where(User.username == username.lower())):
        raise HTTPException(400, "That username is taken")
    user = User(username=username.lower(), password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE, "")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or session.expires_at < now() or not session.user.active:
        raise HTTPException(401, "Please log in")
    if request.method != "GET" and request.headers.get("X-Requested-With") != "dashboard":
        raise HTTPException(403, "Bad request origin")
    return session.user


def owner_only(user: User = Depends(current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(403, "Only the owner can do this")
    return user


class LoginIn(BaseModel):
    username: str
    password: str


def too_many_attempts(username: str) -> bool:
    cutoff = now() - LOCKOUT
    failed_logins[username] = [t for t in failed_logins.get(username, []) if t > cutoff]
    return len(failed_logins[username]) >= MAX_FAILED_LOGINS


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.lower()
    if too_many_attempts(username):
        raise HTTPException(429, "Too many wrong passwords. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.active or not check_password(body.password, user.password_hash):
        failed_logins.setdefault(username, []).append(now())
        raise HTTPException(401, "Wrong username or password")
    failed_logins.pop(username, None)
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=now() + timedelta(days=7)))
    db.commit()
    secure = request.headers.get("X-Forwarded-Proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=secure, max_age=7 * 86400)
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session = db.get(LoginSession, token_hash(request.cookies.get(COOKIE, "")))
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}
