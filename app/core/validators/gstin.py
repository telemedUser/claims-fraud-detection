"""GSTIN validation: format, state code and mod-36 check character. Pure, no I/O."""
from __future__ import annotations

import re

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_STATE_CODES = frozenset(range(1, 39)) | {97}


def check_char(first14: str) -> str:
    """Return the GSTN mod-36 check character for the first 14 characters."""
    if not isinstance(first14, str) or len(first14) != 14:
        raise ValueError("first14 must be a 14-character string")
    total = 0
    for i, ch in enumerate(first14):
        idx = _ALPHABET.find(ch)
        if idx < 0:
            raise ValueError(f"invalid GSTIN character: {ch!r}")
        v = idx * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _ALPHABET[(36 - total % 36) % 36]


def is_valid(gstin: object) -> bool:
    """True if gstin matches the format, has a valid state code, 'Z' at position 14
    and a correct check character."""
    if not isinstance(gstin, str) or not _PATTERN.match(gstin):
        return False
    if int(gstin[:2]) not in _STATE_CODES:
        return False
    return check_char(gstin[:14]) == gstin[14]
