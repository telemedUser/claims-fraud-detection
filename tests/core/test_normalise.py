from decimal import Decimal

from hypothesis import given, strategies as st

from app.core.normalise import (normalise_amount, normalise_date, normalise_fields, normalise_gstin,
                                normalise_name)


def test_dates_to_iso():
    assert normalise_date("05-Jan-2025") == "2025-01-05"
    assert normalise_date("05/01/2025") == "2025-01-05"
    assert normalise_date("2025-01-05") == "2025-01-05"
    assert normalise_date("garbage") is None
    assert normalise_date(None) is None


def test_amounts_to_decimal_string():
    assert normalise_amount("INR 31,850.5") == "31850.50"
    assert normalise_amount("Rs. 1,000") == "1000.00"
    assert normalise_amount("abc") is None


def test_gstin_and_name():
    assert normalise_gstin(" 27abcde1234f1z5 ") == "27ABCDE1234F1Z5"
    assert normalise_gstin("27ABCDE 1234-F1Z5") == "27ABCDE1234F1Z5"
    assert normalise_name("  Asha   KUMAR ") == "asha kumar"


def test_normalise_fields_keeps_originals_and_pages():
    out = normalise_fields([
        {"name": "invoice_date", "value": "05-Jan-2025", "page": 2, "confidence": 0.8},
        {"name": "total", "value": "1,200.00", "page": 1, "confidence": 0.7},
        {"name": "other", "value": "  x  y ", "page": None, "confidence": 0.1},
    ])
    assert [(o.field, o.original, o.normalised, o.page) for o in out] == [
        ("invoice_date", "05-Jan-2025", "2025-01-05", 2),
        ("total", "1,200.00", "1200.00", 1),
        ("other", "  x  y ", "x y", None),
    ]


@given(st.decimals(min_value=0, max_value=10**9, places=2, allow_nan=False, allow_infinity=False))
def test_amount_roundtrip(d):
    formatted = f"INR {d:,.2f}"
    assert Decimal(normalise_amount(formatted)) == d
