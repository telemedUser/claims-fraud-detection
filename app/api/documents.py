"""Uploaded claim documents for investigators. Role: any internal role.

``GET /api/internal/claims/{claim_id}/documents/{index}`` returns the file the customer uploaded at
position ``index`` of the claim's document list. ``?download=1`` asks the browser to save it; otherwise it
is sent inline so the console can preview it.

Only PDF, JPEG and PNG are served with their own content type. Anything else is sent as an
``application/octet-stream`` attachment, so an uploaded HTML or script file can never render in the
console's origin.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app import jobs
from app.api.deps import INVESTIGATE_ROLES, require_roles

router = APIRouter(tags=["internal"])

PREVIEWABLE = {"application/pdf", "image/jpeg", "image/png"}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "document"


@router.get("/api/internal/claims/{claim_id}/documents/{index}",
            dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
def claim_document(claim_id: str, index: int, download: bool = Query(False)):
    job = jobs.JOBS.get(claim_id)
    if job is None:
        raise HTTPException(404, "Claim not found.")
    docs, files = job["documents"], job.get("_files") or []
    if not (0 <= index < len(docs)) or index >= len(files) or not files[index]:
        raise HTTPException(404, "Document not found.")
    meta = docs[index]
    ctype = (meta.get("content_type") or "").split(";")[0].strip().lower()
    inline = ctype in PREVIEWABLE and not download
    if ctype not in PREVIEWABLE:
        ctype = "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    return Response(files[index], media_type=ctype, headers={
        "Content-Disposition": f'{disposition}; filename="{_safe_name(meta["filename"])}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })
