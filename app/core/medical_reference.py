"""Clinical reference lookups for the Medical Review agent. Pure; reads app/rules/medical_reference.v1.yaml.

Illustrative data for fraud screening, not medical advice.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parent.parent / "rules" / "medical_reference.v1.yaml"
_ICD_SHAPE = re.compile(r"^[A-Z]\d{2}(?:\.[0-9A-Z]{1,4})?$")
# "ICD-10: K35.8", "ICD 10 code K35.8", "(ICD10 - J18.9)"
_ICD_LABELLED = re.compile(r"ICD[\s-]?(?:10)?(?:[\s-]?CM)?\s*(?:code)?\s*[:\-]?\s*([A-Za-z]\d{1,2}[0-9A-Za-z.]{0,6})", re.I)
_MEDICINE = re.compile(r"\b(?:Tab|Tablet|Cap|Capsule|Inj|Injection|Syp|Syrup|Drops?|Oint|Ointment|Neb)\.?\s+([A-Za-z][A-Za-z\- ]{2,40})")


@lru_cache(maxsize=1)
def reference() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def disease(disease_id: str | None) -> dict | None:
    return reference()["diseases"].get(disease_id or "")


def primary_icd(disease_id: str | None) -> str | None:
    d = disease(disease_id)
    return d["primary_icd10"] if d else None


def icd_codes(text: str | None) -> list[str]:
    """ICD codes labelled as such in the text, upper case, without duplicates (shape not yet validated)."""
    out: list[str] = []
    for m in _ICD_LABELLED.finditer(text or ""):
        code = m.group(1).upper().rstrip(".")
        if code not in out:
            out.append(code)
    return out


def icd_valid_shape(code: str) -> bool:
    return bool(_ICD_SHAPE.match(code))


def icd_matches(code: str, disease_id: str | None) -> bool:
    d = disease(disease_id)
    return bool(d) and any(code.startswith(p) for p in d["icd10"])


def icd_disease(code: str) -> str | None:
    """The catalogue disease whose ICD prefixes include this code, if any."""
    for did, d in reference()["diseases"].items():
        if any(code.startswith(p) for p in d["icd10"]):
            return did
    return None


def medicines(text: str | None) -> list[str]:
    """Medicine names written after Tab./Cap./Inj./Syp./Drops prefixes."""
    out: list[str] = []
    for m in _MEDICINE.finditer(text or ""):
        name = " ".join(m.group(1).split())
        if name.lower() not in [x.lower() for x in out]:
            out.append(name)
    return out


def medicine_class(name: str) -> str | None:
    low = name.lower()
    for keyword, cls in reference()["medicines"].items():
        if re.search(rf"\b{re.escape(keyword)}", low):
            return cls
    return None


def satisfies(cls: str, expected: str) -> bool:
    """An 'analgesic' expectation is met by any pain or fever medicine."""
    if expected == "analgesic":
        return cls in ("analgesic", "antipyretic", "nsaid", "opioid")
    return cls == expected


def procedures_in(text: str) -> dict[str, list[str]]:
    """disease id -> characteristic procedure keywords found in the text."""
    low = (text or "").lower()
    found: dict[str, list[str]] = {}
    for did, d in reference()["diseases"].items():
        hits = [p for p in d["procedures"] if re.search(rf"\b{re.escape(p)}\b", low)]
        if hits:
            found[did] = hits
    return found


def intensive_in(text: str, services: list[str]) -> list[str]:
    low = (text or "").lower()
    return [s for s in services if re.search(rf"\b{re.escape(s)}\b", low)]
