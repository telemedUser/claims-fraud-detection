"""Writes test documents (medical bill, prescription, medical report) plus a matching claim.json
for a clean case and a suspicious case.

Usage:  python scripts/generate_test_docs.py
Output: test_documents/clean/*  and  test_documents/suspicious/*

Re-run to get fresh claim/invoice IDs and file hashes (avoids duplicate/reuse findings on re-tests).
The customer journey's demo mode (http://localhost:8000/?demo=1) generates the same documents on the fly.
"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import docgen  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "test_documents"

for kind in ("clean", "suspicious"):
    case = docgen.build_case(kind)
    d = OUT / kind
    d.mkdir(parents=True, exist_ok=True)
    for doc_type in docgen.DOC_TYPES:
        (d / f"{doc_type}.pdf").write_bytes(docgen.render(case, doc_type))
    claim_id = f"CL-{uuid.uuid4().hex[:8].upper()}"
    (d / "claim.json").write_text(json.dumps(docgen.claim_json(case, claim_id), indent=2), encoding="utf-8")
    print(f"{kind}: {d}  (policy {case['policy_number']}, claim {claim_id}, "
          f"bill total {case['bill_total']:,.0f}, claimed {case['claimed_amount']:,.0f})")
