from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.core.validators import dates, preauth, totals


def test_recompute_amounts_dicts_and_objects():
    items = [{"amount": "10.10"}, SimpleNamespace(amount=Decimal("0.20")), {"amount": 1}]
    assert totals.recompute(items) == Decimal("11.30")


def test_recompute_quantity_rate_discount_tax():
    items = [{"quantity": 3, "rate": "2.50", "discount": "1.00", "tax": "0.50"}, {"amount": "5"}]
    assert totals.recompute(items) == Decimal("12.00")
    assert totals.recompute([]) == Decimal(0)


def test_recompute_float_is_exact():
    assert totals.recompute([{"amount": 0.1}, {"amount": 0.2}]) == Decimal("0.3")


def test_differs_tolerance_boundary():
    assert not totals.differs(100, "101.00", "1.00")
    assert totals.differs(100, "101.01", "1.00")
    assert totals.differs("99", 100, 0)
    assert not totals.differs(100, 100)


def test_in_window_inclusive():
    s, e = date(2024, 1, 1), date(2024, 12, 31)
    assert dates.in_window(s, s, e) and dates.in_window(e, s, e)
    assert not dates.in_window(date(2023, 12, 31), s, e)
    assert not dates.in_window(date(2025, 1, 1), s, e)


def test_gap_below():
    assert dates.gap_below(date(2024, 1, 1), date(2024, 1, 20), 30)
    assert not dates.gap_below(date(2024, 1, 1), date(2024, 1, 31), 30)


def test_preauth_overrun_boundary():
    assert not preauth.overrun(110000, 100000, 10)
    assert preauth.overrun("110000.01", 100000, 10)
    assert not preauth.overrun(50, 100, 10)
