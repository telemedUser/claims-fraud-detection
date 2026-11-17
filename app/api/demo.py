"""Demo data for the customer journey (?demo=1). Role: public."""
from __future__ import annotations

import uuid
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.seed import docgen

router = APIRouter(tags=["demo"])

DEMO_CASES: "OrderedDict[str, dict]" = OrderedDict()


@router.get("/api/demo/{kind}")
async def demo_case(kind: str):
    if kind not in ("clean", "suspicious"):
        raise HTTPException(404, "Unknown demo case")
    case = docgen.build_case(kind)
    token = uuid.uuid4().hex
    DEMO_CASES[token] = case
    while len(DEMO_CASES) > 50:
        DEMO_CASES.popitem(last=False)
    return {"form": docgen.form_payload(case),
            "documents": [{"doc_type": t, "filename": f"{t}.pdf", "url": f"/api/demo/{token}/{t}.pdf"}
                          for t in docgen.DOC_TYPES]}


@router.get("/api/demo/{token}/{doc_type}.pdf")
async def demo_document(token: str, doc_type: str):
    case = DEMO_CASES.get(token)
    if not case or doc_type not in docgen.DOC_TYPES:
        raise HTTPException(404, "Not found")
    return Response(docgen.render(case, doc_type), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc_type}.pdf"'})
