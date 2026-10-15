"""Import every module that registers job handlers, so the worker (and tests) see all of them."""
from .reservations import jobs as _reservation_jobs  # noqa: F401
from .orders import jobs as _order_jobs  # noqa: F401
from .payments import jobs as _payment_jobs  # noqa: F401
from .notifications import jobs as _notification_jobs  # noqa: F401
from .whatsapp import jobs as _whatsapp_jobs  # noqa: F401
from .reporting import jobs as _reporting_jobs  # noqa: F401
