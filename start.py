import os
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")


def running(url: str) -> bool:
    try:
        urllib.request.urlopen(url + "/health", timeout=1)
        return True
    except OSError:
        return False


def open_when_ready(url: str) -> None:
    for _ in range(60):
        if running(url):
            webbrowser.open(url)
            return
        time.sleep(1)


def main() -> None:
    os.chdir(BACKEND)
    sys.path.insert(0, BACKEND)
    from app.config import config

    url = f"http://localhost:{config().port}"
    if running(url):
        webbrowser.open(url)
        return
    os.makedirs(config().data_dir, exist_ok=True)
    sys.stdout = sys.stderr = open(os.path.join(config().data_dir, "app.log"), "a", buffering=1, encoding="utf-8")
    threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=config().port)


if __name__ == "__main__":
    main()
