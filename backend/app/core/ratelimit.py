"""In-process sliding-window rate limiter.

ponytail: per-process memory. Each installation runs a single API process by default, so this holds;
move to a Postgres/Redis counter if you scale the API to several processes.
"""
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
