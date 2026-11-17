"""Hypothesis strategies for GSTIN tests."""
from hypothesis import strategies as st

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
_ENTITY = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_STATES = [f"{i:02d}" for i in range(1, 39)] + ["97"]


def gstin_base():
    """Format-valid first 14 characters of a GSTIN (valid state code, 'Z' at position 14)."""
    return st.builds(
        lambda s, p, d, l, e: f"{s}{p}{d}{l}{e}Z",
        st.sampled_from(_STATES),
        st.text(_UPPER, min_size=5, max_size=5),
        st.text(_DIGITS, min_size=4, max_size=4),
        st.sampled_from(_UPPER),
        st.sampled_from(_ENTITY),
    )
