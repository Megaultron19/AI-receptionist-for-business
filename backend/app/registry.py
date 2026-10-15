"""Import every module that registers job handlers, so the worker (and tests) see all of them."""
from .reservations import jobs as _reservation_jobs  # noqa: F401
