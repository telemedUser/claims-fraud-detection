"""Property tests for policy date and pre-authorisation rules."""
from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given, settings, strategies as st

from app.core.validators.dates import gap_below, gap_days, in_window
from app.core.validators.preauth import overrun

dates = st.dates(min_value=date(1990, 1, 1), max_value=date(2060, 12, 31))
money = st.decimals(min_value=0, max_value=10**7, places=2)
pcts = st.decimals(min_value=0, max_value=100, places=2)


# Feature: claims-fraud-detection-service, Property 17: Policy date and pre-authorisation rules
# **Validates: Requirements 11.2, 11.3, 11.4**
@settings(max_examples=100)
@given(d=dates, start=dates, end=dates)
def test_in_window_inclusive(d, start, end):
    assert in_window(d, start, end) == (start <= d <= end)
    if start <= end:
        assert in_window(start, start, end)
        assert in_window(end, start, end)


# Feature: claims-fraud-detection-service, Property 17: Policy date and pre-authorisation rules
# **Validates: Requirements 11.2, 11.3, 11.4**
@settings(max_examples=100)
@given(a=dates, b=dates, n=st.integers(min_value=-5, max_value=400))
def test_gap_below(a, b, n):
    assert gap_days(a, b) == (b - a).days
    assert gap_below(a, b, n) == ((b - a).days < n)
    # boundary: gap exactly n is not below n
    if a + timedelta(days=n) <= date(2100, 1, 1) and a + timedelta(days=n) >= date(1900, 1, 1):
        assert not gap_below(a, a + timedelta(days=n), n)
        assert gap_below(a, a + timedelta(days=n - 1), n)


# Feature: claims-fraud-detection-service, Property 17: Policy date and pre-authorisation rules
# **Validates: Requirements 11.2, 11.3, 11.4**
@settings(max_examples=100)
@given(final=money, pre=money, pct=pcts)
def test_overrun_matches_reference(final, pre, pct):
    limit = pre * (Decimal(1) + pct / Decimal(100))
    assert overrun(final, pre, pct) == (final > limit)
    # boundary: exactly at limit is not an overrun; just above is
    assert not overrun(limit, pre, pct)
    assert overrun(limit + Decimal("0.01"), pre, pct)
