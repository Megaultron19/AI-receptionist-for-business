"""Role-based permissions, enforced on every API route via require()."""
ROLES = ("staff", "receptionist", "manager", "owner")

_STAFF = {
    "reservations.view", "tables.view", "orders.view", "orders.kitchen", "menu.view",
    "checkin", "reservations.arrival", "alerts.view",
}
_RECEPTIONIST = _STAFF | {
    "reservations.manage", "waitlist.manage", "tables.block", "inbox.view", "inbox.reply", "handoff.manage",
    "callbacks.manage", "calls.view", "orders.manage", "payments.view", "menu.availability",
}
_MANAGER = _RECEPTIONIST | {
    "menu.manage", "tables.manage", "settings.manage", "payments.refund", "reports.view", "usage.view",
    "audit.view", "health.view",
}
_OWNER = _MANAGER | {"staff.manage", "data.manage", "config.manage"}

PERMISSIONS: dict[str, frozenset[str]] = {
    "staff": frozenset(_STAFF), "receptionist": frozenset(_RECEPTIONIST),
    "manager": frozenset(_MANAGER), "owner": frozenset(_OWNER),
}


def can(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())
