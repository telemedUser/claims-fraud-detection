"""Property tests for invoice total recomputation (Req 11.7)."""
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from app.core.validators.totals import differs, recompute

money = st.decimals(min_value=Decimal("0"), max_value=Decimal("100000"), places=2)
signed_money = st.decimals(min_value=Decimal("-100000"), max_value=Decimal("100000"), places=2)
qty = st.integers(min_value=0, max_value=100)


@st.composite
def line_items(draw):
    """Returns (items, reference_total)."""
    n = draw(st.integers(min_value=0, max_value=10))
    items, ref = [], Decimal(0)
    for _ in range(n):
        discount = draw(st.one_of(st.none(), money))
        tax = draw(st.one_of(st.none(), money))
        if draw(st.booleans()):
            amount = draw(signed_money)
            item = {"amount": amount}
            value = amount
        else:
            q, r = draw(qty), draw(money)
            item = {"quantity": q, "rate": r}
            value = q * r
        if discount is not None:
            item["discount"] = discount
            value -= discount
        if tax is not None:
            item["tax"] = tax
            value += tax
        items.append(item)
        ref += value
    return items, ref


# Feature: claims-fraud-detection-service, Property 16: Invoice totals are recomputed exactly
# **Validates: Requirements 11.7**
@settings(max_examples=100)
@given(data=line_items())
def test_recompute_equals_reference_sum(data):
    items, ref = data
    assert recompute(items) == ref


# Feature: claims-fraud-detection-service, Property 16: Invoice totals are recomputed exactly
# **Validates: Requirements 11.7**
@settings(max_examples=100)
@given(data=line_items(), seed=st.randoms())
def test_recompute_order_independent(data, seed):
    items, ref = data
    shuffled = list(items)
    seed.shuffle(shuffled)
    assert recompute(shuffled) == recompute(items) == ref


# Feature: claims-fraud-detection-service, Property 16: Invoice totals are recomputed exactly
# **Validates: Requirements 11.7**
@settings(max_examples=100)
@given(
    data=line_items(),
    stated=signed_money,
    tol=st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"), places=2),
)
def test_differs_iff_difference_exceeds_tolerance(data, stated, tol):
    items, _ = data
    computed = recompute(items)
    assert differs(stated, computed, tol) == (abs(stated - computed) > tol)


# Feature: claims-fraud-detection-service, Property 16: Invoice totals are recomputed exactly
# **Validates: Requirements 11.7**
@settings(max_examples=100)
@given(data=line_items(), tol=st.decimals(min_value=Decimal("0"), max_value=Decimal("10"), places=2))
def test_stated_equal_to_recomputed_never_differs(data, tol):
    items, _ = data
    assert differs(recompute(items), recompute(items), tol) is False
