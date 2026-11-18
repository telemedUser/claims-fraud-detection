"""SIMULATED laboratory registry: verifies a lab report by its report number. Pure.

Real labs print a report number and a verification code (often as a QR code) that the lab's portal checks.
Here the issuing lab is found from the report-number prefix (``PCL-…`` = Pune Central Laboratory), and the
verification code is an HMAC, under that lab's key, of the report number, sample date, policy number and the
printed results. Changing any result, the date, the number or the policy breaks the code.

Lab keys are synthetic demo values (the registry is simulated and labelled SIMULATED); a real deployment would
call each lab's verification service through the Hospital/Lab verification adapter instead.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from app.seed.seed_data import LABS

SIMULATED = True


def _norm(v: str) -> str:
    return " ".join(str(v or "").lower().split())


def payload(number: str, sample_date: str, policy_number: str, results: list[tuple[str, str]]) -> str:
    rows = ";".join(f"{_norm(n)}={_norm(v)}" for n, v in results)
    return f"{number.strip().upper()}|{sample_date}|{(policy_number or '').strip().upper()}|{rows}"


def lab_for(number: str | None) -> tuple[str, dict] | None:
    prefix = (number or "").split("-", 1)[0].strip().upper()
    lab = LABS.get(prefix)
    return (prefix, lab) if lab else None


def sign(number: str, sample_date: str, policy_number: str, results: list[tuple[str, str]]) -> str:
    found = lab_for(number)
    if not found:
        raise ValueError("unknown lab prefix")
    key = found[1]["key"].encode()
    return hmac.new(key, payload(number, sample_date, policy_number, results).encode(), hashlib.sha256).hexdigest()[:16].upper()


def verify(number: str, sample_date: str, policy_number: str, results: list[tuple[str, str]], code: str) -> bool:
    try:
        expected = sign(number, sample_date, policy_number, results)
    except ValueError:
        return False
    return hmac.compare_digest(expected, (code or "").strip().upper())


# ---------------------------------------------------------------- reading a lab report's text

def parse(text: str) -> dict:
    """Report number, sample date, policy number, results rows and verification code printed on a lab report."""
    from app.core.doc_text import labelled, parse_date

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    results: list[tuple[str, str]] = []
    if "Reference range" in lines:
        rows = []
        for ln in lines[lines.index("Reference range") + 1:]:
            if re.match(r"^(Verification|Authorised|_{3,}|Sample collected|Remarks)", ln, re.I):
                break
            rows.append(ln)
        results = [(rows[i], rows[i + 1]) for i in range(0, len(rows) - 2, 3)]
    first = lambda xs: xs[0] if xs else None  # noqa: E731
    sample = parse_date(first(labelled(text, r"Sample date", r"(\d{1,2}-[A-Za-z]{3}-\d{4})")))
    return {
        "number": first(labelled(text, r"Lab report No\.?", r"([A-Z]{2,5}-[A-Z0-9]{4,12})")),
        "sample_date": sample,
        "policy_number": first(labelled(text, r"Policy No\.?", r"([A-Z0-9][A-Z0-9\-/]{2,30})")),
        "results": results,
        "code": first(labelled(text, r"Verification code", r"([A-F0-9]{16})")),
    }
