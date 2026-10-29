from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import create_user, hash_password, owner_only
from .db import get_db
from .models import LoginSession, User

router = APIRouter(prefix="/api/users")


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "staff"


class PasswordIn(BaseModel):
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "active": u.active}


def find(db: Session, user_id: int, me: User) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == me.id:
        raise HTTPException(400, "You can't change your own login here")
    return user


def log_out_everywhere(db: Session, user: User) -> None:
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))


@router.get("")
def list_users(db: Session = Depends(get_db), _=Depends(owner_only)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("")
def add_user(body: UserIn, db: Session = Depends(get_db), _=Depends(owner_only)):
    if not body.username.strip():
        raise HTTPException(400, "Enter a username")
    user = create_user(db, body.username.strip(), body.password, body.role)
    db.commit()
    return user_out(user)


@router.post("/{user_id}/active")
def set_active(user_id: int, active: bool, db: Session = Depends(get_db), me: User = Depends(owner_only)):
    user = find(db, user_id, me)
    user.active = active
    if not active:
        log_out_everywhere(db, user)
    db.commit()
    return user_out(user)


@router.post("/{user_id}/password")
def set_password(user_id: int, body: PasswordIn, db: Session = Depends(get_db), me: User = Depends(owner_only)):
    user = find(db, user_id, me)
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user.password_hash, user.must_change_password = hash_password(body.password), True
    log_out_everywhere(db, user)
    db.commit()
    return user_out(user)
