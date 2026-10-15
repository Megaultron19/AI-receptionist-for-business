"""Installation commands:  python -m app.cli <command>

  create-owner --name N --email E        create the first owner account (prompts for the password)
  seed-demo [--file F]                   load synthetic demo settings, tables and menu
  export-config [--out F]                restaurant configuration as JSON (no secrets)
  import-config F [--replace-menu]       apply a configuration file
  worker                                 run the background job worker
  purge                                  apply data-retention rules now
  check                                  print configuration problems
"""
import argparse
import getpass
import json
import os
import sys

from .config import get_settings
from .db import SessionLocal


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("create-owner")
    o.add_argument("--name", required=True)
    o.add_argument("--email", required=True)
    o.add_argument("--password", help="omit to be prompted (recommended)")
    s = sub.add_parser("seed-demo")
    s.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "sample-restaurant.json"))
    e = sub.add_parser("export-config")
    e.add_argument("--out")
    i = sub.add_parser("import-config")
    i.add_argument("file")
    i.add_argument("--replace-menu", action="store_true")
    sub.add_parser("worker")
    sub.add_parser("purge")
    sub.add_parser("check")
    a = p.parse_args(argv)

    from . import models, registry  # noqa: F401
    if a.cmd == "worker":
        from .core.jobs import worker_loop
        from .core.logging import setup_logging
        setup_logging(get_settings().log_level)
        worker_loop()
        return 0
    if a.cmd == "check":
        return check()
    with SessionLocal() as db:
        if a.cmd == "create-owner":
            from .auth.service import create_user
            pw = a.password or getpass.getpass("Password (10+ characters): ")
            u = create_user(db, a.name, a.email, pw, "owner")
            db.commit()
            print(f"Owner {u.email} created.")
        elif a.cmd == "seed-demo":
            from .reporting.service import import_config
            print(import_config(db, json.load(open(a.file, encoding="utf-8"))))
            db.commit()
        elif a.cmd == "export-config":
            from .reporting.service import export_config
            out = json.dumps(export_config(db), ensure_ascii=False, indent=2, default=str)
            (open(a.out, "w", encoding="utf-8").write(out) if a.out else print(out))
        elif a.cmd == "import-config":
            from .reporting.service import import_config
            print(import_config(db, json.load(open(a.file, encoding="utf-8")), replace_menu=a.replace_menu))
            db.commit()
        elif a.cmd == "purge":
            from .reporting.service import purge_old_data
            print(purge_old_data(db))
            db.commit()
    return 0


def check() -> int:
    s, problems = get_settings(), []
    if len(s.secret_key) < 32:
        problems.append("SECRET_KEY must be 32+ random characters")
    if not s.public_base_url.startswith("https://") and s.is_production:
        problems.append("PUBLIC_BASE_URL must be https in production (providers require it)")
    if not s.anthropic_api_key:
        problems.append("ANTHROPIC_API_KEY missing: calls and chats will go straight to staff")
    if not (s.plivo_auth_token or s.twilio_auth_token):
        problems.append("No voice provider token (PLIVO_AUTH_TOKEN or TWILIO_AUTH_TOKEN): phone calls won't work")
    if not (s.meta_access_token and s.meta_app_secret and s.meta_verify_token and s.meta_phone_number_id):
        problems.append("WhatsApp settings incomplete (META_*): WhatsApp won't work")
    if not (s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_webhook_secret):
        problems.append("Razorpay settings incomplete: online payments won't work")
    elif s.is_production and s.razorpay_key_id.startswith("rzp_test_"):
        problems.append("Razorpay is in TEST mode (rzp_test_ key) in production")
    for msg in problems:
        print("WARNING:", msg)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
