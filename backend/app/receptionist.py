import os
import shutil
import subprocess
import threading

from fastapi import APIRouter, Depends, HTTPException

from . import razorpay, whatsapp
from .auth import current_user, owner_only
from .config import config
from .db import Session

router = APIRouter(prefix="/api/receptionist")
state = {"on": False, "tunnel": None}
lock = threading.Lock()


def is_on() -> bool:
    return state["on"]


def cloudflared() -> str | None:
    path = config().cloudflared_path
    for candidate in (path, os.path.join("..", path), os.path.join("..", path + ".exe")):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(path)


def tunnel_status() -> str:
    if not config().cloudflare_tunnel_token:
        return "not set up"
    process = state["tunnel"]
    if process and process.poll() is None:
        return "running"
    return "stopped" if not state["on"] else "down"


def start_tunnel() -> None:
    if not config().cloudflare_tunnel_token or tunnel_status() == "running":
        return
    binary = cloudflared()
    if not binary:
        raise RuntimeError("cloudflared was not found. Put it in the app folder or set CLOUDFLARED_PATH.")
    log = open(os.path.join(config().data_dir, "tunnel.log"), "ab")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    state["tunnel"] = subprocess.Popen([binary, "tunnel", "--no-autoupdate", "run", "--token", config().cloudflare_tunnel_token],
                                       stdout=log, stderr=log, creationflags=flags)


def stop_tunnel() -> None:
    process = state["tunnel"]
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
    state["tunnel"] = None


def keep_tunnel_up() -> None:
    with lock:
        if state["on"] and tunnel_status() == "down":
            with Session() as db:
                whatsapp.log_failure(db, "tunnel", "The internet tunnel stopped and was restarted. Check tunnel.log if this keeps happening.")
            start_tunnel()


def status() -> dict:
    c = config()
    return {"on": state["on"], "tunnel": tunnel_status(), "public_url": c.public_url,
            "ready": {"AI": bool(c.anthropic_api_key), "WhatsApp": whatsapp.enabled(), "Phone": bool(c.plivo_webhook_key),
                      "Payments": razorpay.enabled(), "Internet tunnel": bool(c.cloudflare_tunnel_token)}}


@router.get("")
def get_status(_=Depends(current_user)):
    return status()


@router.post("/start")
def start(_=Depends(current_user)):
    with lock:
        try:
            start_tunnel()
        except (RuntimeError, OSError) as e:
            raise HTTPException(400, str(e))
        state["on"] = True
    return status()


@router.post("/stop")
def stop(_=Depends(current_user)):
    with lock:
        state["on"] = False
        stop_tunnel()
    return status()


@router.post("/reload")
def reload_keys(_=Depends(owner_only)):
    with lock:
        config.cache_clear()
        if state["on"]:
            stop_tunnel()
            try:
                start_tunnel()
            except (RuntimeError, OSError) as e:
                raise HTTPException(400, str(e))
    return status()
