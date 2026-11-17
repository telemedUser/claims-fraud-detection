"""Pre-authorisation overrun check (Req 11.4). Pure, Decimal arithmetic."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .totals import to_decimal


def overrun(final: Any, preauth: Any, pct: Any) -> bool:
    """True iff ``final > preauth * (1 + pct/100)``."""
    limit = to_decimal(preauth) * (Decimal(1) + to_decimal(pct) / Decimal(100))
    return to_decimal(final) > limit
