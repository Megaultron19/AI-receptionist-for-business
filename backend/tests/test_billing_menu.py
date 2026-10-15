import pytest

from app.core.errors import DomainError
from app.customers.service import get_or_create
from app.menu.matching import match_item, match_option
from app.orders import service as orders
from app.orders.billing import Line, compute_bill, minimum_payment, rupees

SYS = ("system", None)


def bill(lines, **kw):
    args = dict(order_type="pickup", default_tax_bp=500, prices_include_tax=False, charges=[], discounts=[]) | kw
    return compute_bill(lines, **args)


def test_exclusive_gst_split_into_cgst_sgst():
    b = bill([Line("Paneer Tikka", 2, 28000, 500), Line("Naan", 3, 5000, 500)])
    assert b.subtotal == 71000 and b.tax_total == 3550 and b.total == 74550
    assert b.taxes == [{"rate_bp": 500, "taxable": 71000, "cgst": 1775, "sgst": 1775, "tax": 3550}]


def test_discount_charges_and_mixed_rates():
    b = bill([Line("Thali", 1, 33333, 500), Line("Mocktail", 1, 16667, 1800)],
             discounts=[{"name": "10% off", "percent_bp": 1000, "min_subtotal_paise": 40000},
                        {"name": "5% off", "percent_bp": 500, "min_subtotal_paise": 0}],
             charges=[{"name": "Packaging", "kind": "flat", "value": 2000, "taxable": True, "applies_to": "pickup"},
                      {"name": "Service", "kind": "percent", "value": 500, "taxable": True, "applies_to": "dine_in"}])
    assert b.discount == 5000 and b.discount_name == "10% off"  # best discount wins
    assert [c["name"] for c in b.charges] == ["Packaging"]  # service charge is dine-in only
    # Discount allocated across lines (largest remainder) then taxed per rate; charge taxed at default rate.
    by_rate = {t["rate_bp"]: t for t in b.taxes if t.get("on") != "charges"}
    assert by_rate[500]["taxable"] + by_rate[1800]["taxable"] == 45000
    assert b.total == 45000 + 2000 + b.tax_total


def test_prices_including_tax():
    b = bill([Line("Biryani", 1, 31500, 500)], prices_include_tax=True)
    assert b.tax_total == 1500 and b.taxes[0]["taxable"] == 30000 and b.total == 31500


def test_minimum_payment_rules():
    assert minimum_payment(74550, "full", 0) == 74550
    assert minimum_payment(74550, "percent", 2500) == 18638
    assert minimum_payment(74550, "flat", 20000) == 20000
    assert minimum_payment(15000, "flat", 20000) == 15000
    assert minimum_payment(74550, "none", 0) == 0
    assert minimum_payment(150, "percent", 1000) == 100  # Razorpay minimum ₹1
    assert rupees(12345650) == "₹1,23,456.50" and rupees(5000) == "₹50"


def test_menu_matching(menu):
    items = list(menu.values())
    assert match_item("paneer tikka", items).item.name == "Paneer Tikka"
    assert match_item("पनीर टिक्का", items).item.name == "Paneer Tikka"
    assert match_item("PBM", items).item.name == "Paneer Butter Masala"
    assert match_item("chai", items).item.name == "Masala Chai"
    m = match_item("paneer", items)
    assert m.status == "ambiguous" and {i.name for i in m.candidates} >= {"Paneer Tikka", "Paneer Butter Masala"}
    assert match_item("pizza", items).status == "not_found"
    pbm = menu["pbm"]
    assert match_option("full", pbm.variants)[0].name == "Full"
    v, cands = match_option("medium", pbm.variants)
    assert v is None and cands


def test_order_editing_and_validation(db, menu):
    c = get_or_create(db, "9876500001", "Asha")
    o = orders.create_draft(db, customer=c, channel="whatsapp", actor=SYS)
    with pytest.raises(DomainError, match="Half, Full"):
        orders.add_item(db, o, item_id=menu["pbm"].id, quantity=1, actor=SYS)
    with pytest.raises(DomainError, match="not available"):
        orders.add_item(db, o, item_id=menu["lassi"].id, quantity=1, actor=SYS)
    chai = menu["chai"]
    sugar, extras = chai.addon_groups
    with pytest.raises(DomainError, match="Sugar"):
        orders.add_item(db, o, item_id=chai.id, quantity=1, actor=SYS)
    with pytest.raises(DomainError, match="at most 1"):
        orders.add_item(db, o, item_id=chai.id, quantity=1, actor=SYS, addon_ids=[sugar.addons[0].id, sugar.addons[1].id])
    full = menu["pbm"].variants[1]
    l1 = orders.add_item(db, o, item_id=menu["pbm"].id, variant_id=full.id, quantity=1, actor=SYS)
    l2 = orders.add_item(db, o, item_id=chai.id, quantity=2, actor=SYS, addon_ids=[sugar.addons[1].id, extras.addons[0].id])
    assert l2.unit_price_paise == 7000 and o.subtotal_paise == 38000 + 14000
    orders.update_item(db, o, l1.id, actor=SYS, variant_id=menu["pbm"].variants[0].id, quantity=2)  # change to 2 x Half
    assert o.subtotal_paise == 44000 + 14000 and o.total_paise == 58000 + 2900
    orders.remove_item(db, o, l2.id, actor=SYS)
    assert o.subtotal_paise == 44000 and [l["name"] for l in o.bill["lines"]] == ["Paneer Butter Masala"]
    orders.update_item(db, o, l1.id, actor=SYS, quantity=0)
    assert o.items == [] and o.total_paise == 0
    with pytest.raises(DomainError, match="empty"):
        orders.confirm(db, o, actor=SYS)


def test_menu_change_after_adding_is_caught_at_confirm(db, menu):
    c = get_or_create(db, "9876500001")
    o = orders.create_draft(db, customer=c, channel="whatsapp", actor=SYS)
    orders.add_item(db, o, item_id=menu["tikka"].id, quantity=1, actor=SYS)
    menu["tikka"].available = False
    db.flush()
    with pytest.raises(DomainError, match="not available"):
        orders.confirm(db, o, actor=SYS)


def test_five_minute_target_and_kitchen_load(db, menu, restaurant):
    c = get_or_create(db, "9876500001")
    quick = orders.create_draft(db, customer=c, channel="voice", actor=SYS)
    orders.add_item(db, quick, item_id=menu["tikka"].id, quantity=1, actor=SYS)  # 5 min
    q = orders.kitchen_quote(db, quick)
    assert q["meets_target"] and q["estimate_minutes"] == 5 and q["target_minutes"] == 5
    slow = orders.create_draft(db, customer=c, channel="voice", actor=SYS)
    orders.add_item(db, slow, item_id=menu["pbm"].id, variant_id=menu["pbm"].variants[0].id, quantity=1, actor=SYS)
    q = orders.kitchen_quote(db, slow)
    assert not q["meets_target"] and q["estimate_minutes"] == 12 and "longer" in q["reasons"][0]
    restaurant.kitchen_parallel_orders = 1
    restaurant.min_payment_type = "none"
    db.flush()
    orders.confirm(db, slow, actor=SYS)  # no payment needed -> straight to the kitchen
    assert slow.status == "submitted" and slow.invoice_number
    q = orders.kitchen_quote(db, quick)
    assert q["estimate_minutes"] == 5 + 12 and not q["meets_target"]  # queued behind the busy kitchen


def test_state_machine_rejects_invalid_moves(db, menu):
    c = get_or_create(db, "9876500001")
    o = orders.create_draft(db, customer=c, channel="whatsapp", actor=SYS)
    for bad in ("accepted", "paid", "ready", "completed", "refunded"):
        with pytest.raises(DomainError):
            orders.transition(db, o, bad, actor=SYS)
