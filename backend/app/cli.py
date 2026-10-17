import argparse
import getpass

from .auth import create_user
from .db import Base, Session, engine


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-user")
    add.add_argument("username")
    add.add_argument("--role", choices=("owner", "staff"), default="owner")
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    if args.command == "add-user":
        password = getpass.getpass("Password: ")
        with Session() as db:
            create_user(db, args.username, password, args.role)
            db.commit()
        print(f"User {args.username} created")


if __name__ == "__main__":
    main()
