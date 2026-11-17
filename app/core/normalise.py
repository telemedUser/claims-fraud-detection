"""Pure normalisation of extracted fields. Originals are always kept alongside the result."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y",
                 "%d/%m/%y", "%d-%m-%y", "%d/%b/%Y")


@dataclass(frozen=True)
class NormalisedField:
    field: str
    original: str | None
    normalised: str | None
    page: int | None
    source_field: str | None


def normalise_date(value: str | None) -> str | None:
    """ISO date (YYYY-MM-DD) or None. Slash and dash numeric dates are read day-first."""
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalise_amount(value: str | None) -> str | None:
    """Decimal string with two places, or None. Removes currency markers and separators."""
    if value is None:
        return None
    s = re.sub(r"(?i)\b(inr|rs)\b\.?|₹", "", str(value))
    s = re.sub(r"[,\s]", "", s)
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        return str(Decimal(s).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def normalise_gstin(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[\s\-]", "", str(value)).upper() or None


def normalise_name(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip().casefold() or None


def normalise_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", "", str(value)).upper() or None


_NORMALISERS = {
    "invoice_date": normalise_date, "date": normalise_date,
    "total": normalise_amount, "amount": normalise_amount,
    "gstin": normalise_gstin,
    "invoice_number": normalise_identifier,
    "name": normalise_name, "patient_name": normalise_name, "hospital_name": normalise_name,
}


def normalise_fields(fields: list[dict[str, Any]]) -> list[NormalisedField]:
    """One NormalisedField per extracted field, in order. Unknown field names are whitespace-trimmed."""
    out: list[NormalisedField] = []
    for f in fields:
        name = str(f.get("name"))
        raw = f.get("value")
        original = None if raw is None else str(raw)
        fn = _NORMALISERS.get(name)
        normalised = fn(original) if fn else (re.sub(r"\s+", " ", original).strip() if original is not None else None)
        out.append(NormalisedField(name, original, normalised, f.get("page"), name))
    return out


__all__ = ["NormalisedField", "normalise_date", "normalise_amount", "normalise_gstin", "normalise_name",
           "normalise_identifier", "normalise_fields"]
