import argparse
import getpass
import secrets

from sqlalchemy import delete, select

from .auth import create_user, hash_password
from .db import Session, engine, migrate
from .models import LoginSession, User


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-user")
    add.add_argument("username")
    add.add_argument("--role", choices=("owner", "staff"), default="owner")
    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    args = parser.parse_args()
    migrate(engine)
    if args.command == "add-user":
        password = getpass.getpass("Password: ")
        with Session() as db:
            create_user(db, args.username, password, args.role)
            db.commit()
        print(f"User {args.username} created")
    if args.command == "reset-password":
        print(reset_password(args.username))


def reset_password(username: str) -> str:
    with Session() as db:
        user = db.scalar(select(User).where(User.username == username.strip().lower()))
        if not user:
            names = ", ".join(db.scalars(select(User.username).order_by(User.username)))
            return f"No login called {username}. Logins: {names or 'none'}"
        temporary = secrets.token_urlsafe(8)
        user.password_hash, user.must_change_password, user.active = hash_password(temporary), True, True
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.commit()
        return f"Temporary password for {user.username}: {temporary}\nThey will be asked to choose a new one when they log in."


if __name__ == "__main__":
    main()
