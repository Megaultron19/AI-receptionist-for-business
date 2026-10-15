"""Bill calculation in integer paise. Pure functions, no I/O: the single source of every amount shown to
customers, sent to Razorpay or printed on an invoice."""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def pct(amount: int, bp: int) -> int:
    """amount * bp / 10000, rounded half-up to the paisa."""
    return int((Decimal(amount) * bp / Decimal(10000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class Line:
    name: str
    quantity: int
    unit_price_paise: int
    tax_rate_bp: int
    detail: str = ""  # variant / add-ons, for display

    @property
    def total(self) -> int:
        return self.unit_price_paise * self.quantity


@dataclass
class Bill:
    lines: list[dict[str, Any]]
    subtotal: int
    discount: int
    discount_name: str
    charges: list[dict[str, Any]]
    taxes: list[dict[str, Any]]  # per rate: taxable, cgst, sgst
    tax_total: int
    total: int
    prices_include_tax: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def allocate(amount: int, weights: list[int]) -> list[int]:
    """Split `amount` across weights so the parts sum exactly (largest remainder)."""
    total = sum(weights)
    if not total or not amount:
        return [0] * len(weights)
    raw = [Decimal(amount) * w / total for w in weights]
    parts = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - parts[i], reverse=True)
    for i in order[: amount - sum(parts)]:
        parts[i] += 1
    return parts


def compute_bill(lines: list[Line], *, order_type: str, default_tax_bp: int, prices_include_tax: bool,
                 charges: list[dict[str, Any]], discounts: list[dict[str, Any]]) -> Bill:
    subtotal = sum(l.total for l in lines)

    applicable = [d for d in discounts if d.get("active", True) and subtotal >= d.get("min_subtotal_paise", 0)]
    best = max(applicable, key=lambda d: pct(subtotal, d["percent_bp"]), default=None)
    discount = pct(subtotal, best["percent_bp"]) if best else 0
    net_lines = [l.total - share for l, share in zip(lines, allocate(discount, [l.total for l in lines]))]
    after_discount = subtotal - discount

    charge_rows, taxable_charges = [], 0
    for c in charges:
        if c.get("applies_to", "all") not in ("all", order_type):
            continue
        amt = pct(after_discount, c["value"]) if c["kind"] == "percent" else c["value"]
        if amt:
            charge_rows.append({"name": c["name"], "amount": amt, "taxable": c.get("taxable", True)})
            taxable_charges += amt if c.get("taxable", True) else 0
    charges_total = sum(c["amount"] for c in charge_rows)

    by_rate: dict[int, int] = {}
    for l, net in zip(lines, net_lines):
        by_rate[l.tax_rate_bp] = by_rate.get(l.tax_rate_bp, 0) + net
    taxes, tax_total = [], 0
    for rate, base in sorted(by_rate.items()):
        if prices_include_tax:
            # Menu prices already include GST: back it out of the line value.
            tax = base - int((Decimal(base) * 10000 / (10000 + rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            taxable = base - tax
        else:
            tax, taxable = pct(base, rate), base
        taxes.append({"rate_bp": rate, "taxable": taxable, "cgst": tax // 2, "sgst": tax - tax // 2, "tax": tax})
        tax_total += tax
    if taxable_charges and default_tax_bp:
        tax = pct(taxable_charges, default_tax_bp)  # charges are always priced exclusive of tax
        taxes.append({"rate_bp": default_tax_bp, "taxable": taxable_charges, "cgst": tax // 2, "sgst": tax - tax // 2,
                      "tax": tax, "on": "charges"})
        tax_total += tax

    if prices_include_tax:
        line_tax = sum(t["tax"] for t in taxes if t.get("on") != "charges")
        total = after_discount + charges_total + (tax_total - line_tax)
    else:
        total = after_discount + charges_total + tax_total

    return Bill(
        lines=[{"name": l.name, "detail": l.detail, "quantity": l.quantity, "unit_price": l.unit_price_paise,
                "total": l.total, "tax_rate_bp": l.tax_rate_bp} for l in lines],
        subtotal=subtotal, discount=discount, discount_name=best["name"] if best else "",
        charges=charge_rows, taxes=taxes, tax_total=tax_total, total=total, prices_include_tax=prices_include_tax,
    )


def minimum_payment(total: int, kind: str, value: int) -> int:
    """Amount to collect before the order goes to the kitchen. Razorpay's minimum is ₹1."""
    if total <= 0 or kind == "none":
        return 0
    due = {"full": total, "percent": pct(total, value), "flat": min(value, total)}[kind]
    return min(total, max(due, 100)) if due else 0


def rupees(paise: int) -> str:
    """Indian digit grouping: ₹1,23,456.50"""
    r, p = divmod(abs(paise), 100)
    digits = str(r)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        digits = f"{head},{tail}"
    return ("-" if paise < 0 else "") + f"₹{digits}" + (f".{p:02d}" if p else "")
