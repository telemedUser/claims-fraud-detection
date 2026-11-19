"""Demo data for the customer journey (?demo=1). Role: public.

``GET /api/demo/{kind}`` builds a fictional case (``app/seed/docgen.py``) and returns the journey form values, a
token, and links to its generated PDFs. A claim submitted with that token is a demo claim: it is stored and shown in
the console like any other, but kept out of the history later claims are compared with, so every scenario gives the
same result each time it is run. Demo routes are for test environments only and must be disabled in production.
"""
from __future__ import annotations

import json
import uuid
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.seed import docgen

router = APIRouter(tags=["demo"])

DEMO_CASES: "OrderedDict[str, dict]" = OrderedDict()
KINDS = ("clean", "suspicious", *docgen.SCENARIO_KINDS)


@router.get("/api/demo/{kind}")
async def demo_case(kind: str):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown demo case")
    case = docgen.build_case(kind)
    token = uuid.uuid4().hex
    DEMO_CASES[token] = case
    while len(DEMO_CASES) > 50:
        DEMO_CASES.popitem(last=False)
    return {"kind": kind, "token": token, "form": docgen.form_payload(case),
            "documents": [{"doc_type": t, "filename": f"{t}.pdf", "url": f"/api/demo/{token}/{t}.pdf"}
                          for t in docgen.DOC_TYPES]}


@router.get("/api/demo/{token}/{doc_type}.pdf")
async def demo_document(token: str, doc_type: str):
    case = DEMO_CASES.get(token)
    if not case or doc_type not in docgen.DOC_TYPES:
        raise HTTPException(404, "Not found")
    return Response(docgen.render(case, doc_type), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc_type}.pdf"'})


def is_demo_submission(token: str, payload: str) -> bool:
    """True when ``token`` is a generated demo case and the submitted bill number is that case's, so a token
    cannot be reused to keep an unrelated claim out of the history."""
    case = DEMO_CASES.get(token or "")
    if case is None:
        return False
    try:
        number = json.loads(payload)["invoice"]["invoice_number"]
    except (ValueError, KeyError, TypeError):
        return False
    return str(number).strip() == case["invoice_number"]
