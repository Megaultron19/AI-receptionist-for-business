import getpass
import os
import plistlib
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
APP_NAME = "Restaurant Receptionist"


def create_owner() -> None:
    from app.auth import create_user
    from app.db import Session, engine, migrate
    from app.models import User

    migrate(engine)
    with Session() as db:
        if db.query(User).count():
            return
        print("\nCreate the owner login for the dashboard.")
        username = input("Username: ").strip() or "owner"
        while True:
            password = getpass.getpass("Password (at least 8 characters): ")
            if len(password) >= 8 and password == getpass.getpass("Type it again: "):
                break
            print("Passwords did not match or were too short, try again.")
        create_user(db, username, password, "owner")
        db.commit()


def windows_shortcut() -> str:
    target = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop", APP_NAME + ".lnk")
    script = (f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{desktop}"); $s.TargetPath = "{target}"; '
              f'$s.Arguments = \'"{os.path.join(ROOT, "start.py")}"\'; $s.WorkingDirectory = "{ROOT}"; $s.Save()')
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    return desktop


def mac_app() -> str:
    app = os.path.join(os.path.expanduser("~/Desktop"), APP_NAME + ".app")
    shutil.rmtree(app, ignore_errors=True)
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    launcher = os.path.join(app, "Contents", "MacOS", "receptionist")
    with open(launcher, "w") as f:
        f.write(f'#!/bin/sh\nexec "{os.path.join(ROOT, ".venv", "bin", "python")}" "{os.path.join(ROOT, "start.py")}"\n')
    os.chmod(launcher, 0o755)
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleName": APP_NAME, "CFBundleExecutable": "receptionist", "CFBundleIdentifier": "local.restaurant.receptionist",
                       "CFBundlePackageType": "APPL"}, f)
    return app


def main() -> None:
    os.chdir(BACKEND)
    sys.path.insert(0, BACKEND)
    if not os.path.exists(".env"):
        shutil.copy(".env.example", ".env")
        print(f"Created {os.path.join(BACKEND, '.env')}. Fill in the keys before going live, see docs/SETUP.md.")
    create_owner()
    if sys.platform == "win32":
        print("Desktop shortcut:", windows_shortcut())
    elif sys.platform == "darwin":
        print("Desktop app:", mac_app())
    print("\nDone. Open the desktop icon, log in and press Start.")


if __name__ == "__main__":
    main()
