import pytest
from hypothesis import given, strategies as st

from app.core.validators.gstin import check_char, is_valid

KNOWN_VALID = ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"]


@pytest.mark.parametrize("g", KNOWN_VALID)
def test_known_valid(g):
    assert check_char(g[:14]) == g[14]
    assert is_valid(g)


def test_wrong_check_char():
    assert not is_valid("27AAPFU0939F1ZX")


def test_bad_state_code():
    for sc in ("00", "39", "50", "96", "98"):
        g = sc + "AAPFU0939F1Z"
        g = g[:14] if len(g) > 14 else g
        full = sc + "AAPFU0939F1Z" + check_char(sc + "AAPFU0939F1Z")
        assert not is_valid(full)


def test_state_97_accepted():
    base = "97AAPFU0939F1Z"
    assert is_valid(base + check_char(base))


def test_z_position_required():
    base = "27AAPFU0939F1A"
    assert not is_valid(base + check_char(base))


@pytest.mark.parametrize("bad", ["", "27AAPFU0939F1Z", "27aapfu0939f1zv", "27AAPFU0939F0ZV", None, 5])
def test_bad_format(bad):
    assert not is_valid(bad)


def test_check_char_rejects_bad_input():
    with pytest.raises(ValueError):
        check_char("short")
    with pytest.raises(ValueError):
        check_char("27AAPFU0939F1Z!")


def test_seeded_gstins_report():
    seeded = ["27AAACC1111A1ZQ", "27AAACS2222B1Z2", "27AAACL4444D1ZT", "29AAACG5555E1ZM"]
    for g in seeded:
        assert is_valid(g)


_st_state = st.sampled_from([f"{i:02d}" for i in range(1, 39)] + ["97"])
_gstin_body = st.builds(
    lambda s, p, d, l, e: f"{s}{p}{d}{l}{e}Z",
    _st_state,
    st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=5, max_size=5),
    st.text("0123456789", min_size=4, max_size=4),
    st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=1),
    st.text("123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=1),
)


@given(_gstin_body)
def test_generated_with_check_char_is_valid_and_altered_is_not(body):
    g = body + check_char(body)
    assert is_valid(g)
    other = "0" if g[14] != "0" else "1"
    assert not is_valid(g[:14] + other)
