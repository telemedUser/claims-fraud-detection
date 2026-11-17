"""Policy date checks (Req 11.2, 11.3). Pure functions."""
from __future__ import annotations

from datetime import date


def in_window(d: date, start: date, end: date) -> bool:
    """True iff ``start <= d <= end`` (both ends inclusive)."""
    return start <= d <= end


def gap_days(earlier: date, later: date) -> int:
    """Whole days from ``earlier`` to ``later`` (negative if ``later`` is before)."""
    return (later - earlier).days


def gap_below(earlier: date, later: date, min_days: int) -> bool:
    """True iff the gap between the dates is strictly below ``min_days``."""
    return gap_days(earlier, later) < min_days
