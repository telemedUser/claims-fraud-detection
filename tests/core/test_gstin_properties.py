from hypothesis import given, settings, strategies as st

from app.core.validators.gstin import check_char, is_valid
from tests.strategies.gstin import gstin_base

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# Feature: claims-fraud-detection-service, Property 14: GSTIN check character round trip
# Validates: Requirements 11.5
@settings(max_examples=100)
@given(base=gstin_base(), data=st.data())
def test_gstin_check_char_round_trip(base, data):
    gstin = base + check_char(base)
    assert is_valid(gstin)

    # The per-position contribution map is a bijection mod 36 (weight 1: identity;
    # weight 2: evens for idx<18, odds for idx>=18), so any single-character
    # substitution anywhere in the 15 characters must make the GSTIN invalid.
    pos = data.draw(st.integers(min_value=0, max_value=14))
    repl = data.draw(st.sampled_from([c for c in _ALPHABET if c != gstin[pos]]))
    mutated = gstin[:pos] + repl + gstin[pos + 1:]
    assert not is_valid(mutated)
