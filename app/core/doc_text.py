"""Document text and the fields printed on claim documents. Text comes from the extraction adapter (pypdf,
no OCR); parsing is pure regex.

Used by the Provider Profile, Document Scan and Invoice Check agents. Field values can contain personal data
(patient name, policy number): they are compared locally and only reach the LLM through ``app/core/redact.py``.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_DATE = r"(\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{2,4}|\d{4}-\d{2}-\d{2})"
_AMOUNT = r"(?:INR|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
_DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%y")


def document_texts(documents) -> list[tuple[object, str]]:
    """(document, text) for each document with machine-readable text. Unreadable or image-only files are skipped."""
    from app.adapters import get_extraction
    from app.adapters.errors import AdapterError

    try:
        extractor = get_extraction()
    except AdapterError:
        return []
    out = []
    for doc in documents:
        if not getattr(doc, "data", None):
            continue
        try:
            result = extractor.extract(doc.data, doc.content_type)
        except Exception:  # unreadable files are reported by Document Scan
            continue
        text = "\n".join(p.get("text") or "" for p in result.pages).strip()
        if text:
            out.append((doc, text))
    return out


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def labelled(text: str, label: str, value: str = r"([^\n|]{1,80})") -> list[str]:
    """Values printed after ``label`` on the same line or the next line, in order."""
    rx = re.compile(rf"(?:^|\n|\|)\s*{label}\s*[:\-]?\s*\n?\s*{value}", re.I)
    return [m.group(1).strip() for m in rx.finditer(text or "")]


def fields(text: str) -> dict:
    """Fields printed on a claim document. Missing fields are None or empty lists."""
    t = text or ""
    first = lambda xs: xs[0] if xs else None  # noqa: E731
    admitted = [parse_date(v) for v in labelled(t, "Admitted", _DATE)]
    discharged = [parse_date(v) for v in labelled(t, "Discharged", _DATE)]
    totals = [parse_amount(v) for v in labelled(t, r"(?:Amount payable|Grand Total|Total Amount|Bill Total)", _AMOUNT)]
    return {
        "patient": first(labelled(t, r"Patient(?! ID)")),
        "policy_number": first(labelled(t, r"Policy No\.?", r"([A-Z0-9][A-Z0-9\-/]{2,30})")),
        "bill_number": first(labelled(t, r"(?:Bill|Invoice) No\.?", r"([A-Za-z0-9][A-Za-z0-9/\-]{2,40})")),
        "bill_date": parse_date(first(labelled(t, r"(?:Bill|Invoice) Date", _DATE))),
        "admitted": [d for d in admitted if d],
        "discharged": [d for d in discharged if d],
        "diagnosis": first(labelled(t, r"(?:Final diagnosis|Diagnosis)")),
        "totals": [x for x in totals if x is not None],
        "amount_paid": parse_amount(first(labelled(t, r"Amount paid", _AMOUNT))),
        "balance_due": parse_amount(first(labelled(t, r"Balance due", _AMOUNT))),
        "payment_mode": first(labelled(t, r"Payment mode")),
        "receipt_number": first(labelled(t, r"Receipt No\.?", r"([A-Za-z0-9][A-Za-z0-9/\-]{2,40})")),
        "paid_on": parse_date(first(labelled(t, r"Paid on", _DATE))),
        "gst": {k: [x for x in (parse_amount(v) for v in labelled(t, k, _AMOUNT)) if x is not None]
                for k in ("CGST", "SGST", "IGST")},
    }
