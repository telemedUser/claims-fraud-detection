"""Invoice total validation. Pure, Decimal-only arithmetic (Req 11.7).

Line items are dicts or objects (e.g. pydantic models) with these fields:

* ``amount``: the line total. Used as-is when present and not None.
* ``quantity`` and ``rate``: used as ``quantity * rate`` when ``amount`` is absent.
* ``discount`` and ``tax``: optional; subtracted / added to the line value.

A line with neither ``amount`` nor ``rate`` contributes zero.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable


def to_decimal(value: Any) -> Decimal:
    """Convert int/str/Decimal/float to Decimal (floats via ``str`` to avoid binary noise)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def _get(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def line_total(item: Any) -> Decimal:
    """Computed value of one line item (see module docstring)."""
    amount = _get(item, "amount")
    if amount is not None:
        value = to_decimal(amount)
    else:
        rate = _get(item, "rate")
        if rate is None:
            value = Decimal(0)
        else:
            qty = _get(item, "quantity")
            value = to_decimal(rate) * (to_decimal(qty) if qty is not None else Decimal(1))
    discount = _get(item, "discount")
    tax = _get(item, "tax")
    if discount is not None:
        value -= to_decimal(discount)
    if tax is not None:
        value += to_decimal(tax)
    return value


def recompute(line_items: Iterable[Any]) -> Decimal:
    """Sum of line totals as an exact Decimal."""
    total = Decimal(0)
    for item in line_items:
        total += line_total(item)
    return total


def differs(stated: Any, computed: Any, tolerance: Any = 0) -> bool:
    """True iff ``abs(stated - computed) > tolerance``."""
    return abs(to_decimal(stated) - to_decimal(computed)) > to_decimal(tolerance)
