"""In-process sliding-window rate limiter. Counters live in process memory, which is correct for the
default single API process per installation; use a shared store if the API is scaled out."""
import threading
import time
from collections import defaultdict, deque

from .errors import DomainError

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def check(key: str, limit: int, per_seconds: float) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - per_seconds:
            q.popleft()
        if len(q) >= limit:
            raise DomainError("Too many requests. Please wait and try again.", "rate_limited", 429)
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
