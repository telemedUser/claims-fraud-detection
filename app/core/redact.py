"""Removes personal data from document text before it is sent to the LLM (Requirement 10.1). Pure.

Removed: the claimant's name (and each part of it), the policy number, the claimant id, the value printed
after "Patient", "Patient ID", "Policy No" and "Name" labels, dates of birth, phone numbers, e-mail addresses,
12-digit identity numbers (Aadhaar-like), PAN-like codes and personal addresses after "Address:".
Provider details (hospital, doctor, GSTIN) are kept: they are needed for the analysis and are not the
claimant's personal data.
"""
from __future__ import annotations

import re

_PHONE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_DOB = re.compile(r"(?i)\b(D\.?O\.?B\.?|Date of birth|Born)\s*[:\-]?\s*\S+")
_LABELS = re.compile(r"(?im)((?:^|\|)\s*(?:Patient(?: name)?|Patient ID|Policy No\.?|Name|Address)\s*[:\-]?\s*\n?\s*)([^\n|]{1,80})")


def redact(text: str, *, name: str | None = None, policy_number: str | None = None,
           claimant_id: str | None = None) -> str:
    """Text with the claimant's personal data replaced by placeholders such as ``[PATIENT]``."""
    t = text or ""
    t = _LABELS.sub(lambda m: m.group(1) + "[REDACTED]", t)
    for value, token in ((policy_number, "[POLICY]"), (claimant_id, "[CLAIMANT]")):
        if value:
            t = re.sub(re.escape(value), token, t, flags=re.I)
    if name:
        t = re.sub(re.escape(name), "[PATIENT]", t, flags=re.I)
        for part in re.split(r"[\s.]+", name):
            if len(part) >= 3:  # initials are too short to match safely
                t = re.sub(rf"\b{re.escape(part)}\b", "[PATIENT]", t, flags=re.I)
    t = _DOB.sub(r"\1 [REDACTED]", t)
    t = _EMAIL.sub("[EMAIL]", t)
    t = _PAN.sub("[ID]", t)
    t = _AADHAAR.sub("[ID]", t)
    t = _PHONE.sub("[PHONE]", t)
    return t
