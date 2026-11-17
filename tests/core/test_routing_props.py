# Feature: claims-fraud-detection-service, Property 5: Routing is total and respects band boundaries
"""Validates: Requirements 5.6"""
from hypothesis import example, given, settings, strategies as st

from app.core.risk_config import Bands
from app.core.routing import route

ROUTES = {"low", "manual_review", "investigate"}
DEFAULT = Bands(review_at=30.0, investigate_at=60.0)

_finite = dict(allow_nan=False, allow_infinity=False)


@st.composite
def bands_st(draw):
    review = draw(st.floats(min_value=0.0, max_value=100.0, exclude_min=True, exclude_max=True, **_finite))
    inv = draw(st.floats(min_value=review, max_value=100.0, exclude_min=True, **_finite))
    return Bands(review_at=review, investigate_at=inv)


scores = st.floats(min_value=0.0, max_value=100.0, **_finite)


def reference(score, b):
    if score >= b.investigate_at:
        return "investigate"
    if score >= b.review_at:
        return "manual_review"
    return "low"


@settings(max_examples=100)
@given(bands=bands_st(), score=scores)
@example(bands=DEFAULT, score=29.9)
@example(bands=DEFAULT, score=30.0)
@example(bands=DEFAULT, score=59.9)
@example(bands=DEFAULT, score=60.0)
def test_route_total_and_matches_reference(bands, score):
    result = route(score, bands)
    assert result in ROUTES
    assert result == reference(score, bands)


@settings(max_examples=100)
@given(bands=bands_st(), a=scores, b=scores)
def test_route_monotone(bands, a, b):
    order = {"low": 0, "manual_review": 1, "investigate": 2}
    lo, hi = sorted((a, b))
    assert order[route(lo, bands)] <= order[route(hi, bands)]


def test_default_boundaries():
    assert route(29.9, DEFAULT) == "low"
    assert route(30.0, DEFAULT) == "manual_review"
    assert route(59.9, DEFAULT) == "manual_review"
    assert route(60.0, DEFAULT) == "investigate"
