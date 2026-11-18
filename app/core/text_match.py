"""Text helpers for comparing provider details printed on documents with the registry. Pure, no I/O.

Matching is deterministic: exact substring first, then a fuzzy ratio over windows of the same number of
words (difflib), so "City General Hospital" still matches "CITY GENERAL HOSPITAL, PUNE" or a one-letter OCR slip.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_TITLES = re.compile(r"\b(dr|doctor|mr|mrs|ms|prof)\b\.?", re.I)
_NON_WORD = re.compile(r"[^a-z0-9]+")
_GSTIN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b")
# "Reg. No: MMC-2009-11872", "Registration No. KMC/2011/55302", "(MMC-2009-11872)"
_REG_LABELLED = re.compile(r"Reg(?:istration)?\.?\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z]{2,6}[-/ ]?\d{2,4}[-/ ]?\d{3,7})", re.I)
_REG_BARE = re.compile(r"\b([A-Z]{2,6}[-/]\d{4}[-/]\d{3,7})\b")


def normalise_name(name: str | None) -> str:
    """Lower case, titles (Dr., Mr.) removed, punctuation collapsed to single spaces."""
    s = _TITLES.sub(" ", str(name or "").lower())
    return " ".join(_NON_WORD.sub(" ", s).split())


def normalise_id(value: str | None) -> str:
    """Identifier compared without separators or case: 'mmc-2009-11872' == 'MMC 2009 11872'."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def name_match_score(name: str | None, text: str | None) -> float:
    """Best match of ``name`` anywhere in ``text``, 0..1. 1.0 means an exact (normalised) occurrence."""
    target = normalise_name(name)
    hay = normalise_name(text)
    if not target or not hay:
        return 0.0
    if f" {target} " in f" {hay} ":
        return 1.0
    words = hay.split()
    n = len(target.split())
    best = 0.0
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(words) - size + 1)):
            window = " ".join(words[i:i + size])
            best = max(best, SequenceMatcher(None, target, window).ratio())
    return round(best, 3)


def find_gstins(text: str | None) -> list[str]:
    """GSTIN-shaped tokens in the text, upper case, in order, without duplicates."""
    out: list[str] = []
    for m in _GSTIN.finditer(str(text or "").upper()):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def find_registration_numbers(text: str | None) -> list[str]:
    """Medical registration numbers as printed, without duplicates (compared with ``normalise_id``)."""
    t = str(text or "")
    out: list[str] = []
    seen: set[str] = set()
    for rx in (_REG_LABELLED, _REG_BARE):
        for m in rx.finditer(t):
            raw = m.group(1).strip()
            key = normalise_id(raw)
            if key and key not in seen:
                seen.add(key)
                out.append(raw)
    return out
