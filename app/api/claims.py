"""Internal claim routes (role protected). Requirements 7.1, 16.1.

* ``POST /api/internal/claims``: investigator-created claim; same checks and processing as the customer path.
* ``GET /api/internal/claims``: list with filters. ``assignee`` is accepted but not yet applied, because
  claims carry no assignee until the case-management work (not yet built) adds one.
* ``GET /api/internal/claims/{id}``: full detail.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from app import jobs
from app.api.common import accept_submission
from app.api.deps import ASSESS_ROLES, INVESTIGATE_ROLES, require_roles
from app.db.repos import DISEASES

router = APIRouter(tags=["internal"])

# Queue bands as produced by routing: low (auto approve), manual_review, investigate.
_BAND_DECISION = {"low": "auto_approve", "manual_review": "manual_review", "investigate": "investigate"}


@router.post("/api/internal/claims", status_code=202, dependencies=[Depends(require_roles(*ASSESS_ROLES))])
async def create_internal_claim(payload: str = Form(..., description="ClaimSubmission as JSON"),
                                documents: list[UploadFile] = File(default=[]),
                                document_types: str = Form("[]", description="JSON list of doc types, same order as documents")):
    return {"claim_id": await accept_submission(payload, documents, document_types)}


def _matches(job: dict, summary: dict, *, band, status, provider, date_from, date_to, category) -> bool:
    claim = job["claim"]
    if band and summary["decision"] != _BAND_DECISION[band]:
        return False
    if status and job["status"] != status:
        return False
    if provider:
        needle = provider.strip().lower()
        hay = (claim.hospital_id, claim.doctor_id, str(summary["hospital"]))
        if not any(needle in h.lower() for h in hay if h):
            return False
    submitted = datetime.fromisoformat(job["submitted_at"]).date()
    if date_from and submitted < date_from:
        return False
    if date_to and submitted > date_to:
        return False
    if category:
        cat = (DISEASES.get(claim.disease_id or "") or {}).get("category", "")
        if cat.lower() != category.strip().lower():
            return False
    return True


@router.get("/api/internal/claims", dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
async def list_internal_claims(
        response: Response,
        band: Literal["low", "manual_review", "investigate"] | None = Query(None, description="Queue band"),
        status: Literal["processing", "completed", "failed"] | None = Query(None),
        provider: str | None = Query(None, max_length=100, description="Hospital id/name or doctor id (substring)"),
        date_from: date | None = Query(None, description="Submitted on or after (UTC date)"),
        date_to: date | None = Query(None, description="Submitted on or before (UTC date)"),
        assignee: str | None = Query(None, max_length=100, description="Accepted; not yet applied (no assignee data)"),
        category: str | None = Query(None, max_length=100, description="Disease category, e.g. Cardiac")):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from cannot be after date_to.")
    if assignee:
        response.headers["X-Filters-Not-Applied"] = "assignee"
    rows = []
    for job in sorted(jobs.JOBS.values(), key=lambda j: j["submitted_at"], reverse=True):
        summary = jobs.internal_summary(job)
        if _matches(job, summary, band=band, status=status, provider=provider, date_from=date_from,
                    date_to=date_to, category=category):
            rows.append(summary)
    return rows


@router.get("/api/internal/claims/{claim_id}", dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
async def get_internal_claim(claim_id: str):
    job = jobs.JOBS.get(claim_id)
    if not job:
        raise HTTPException(404, "Claim not found")
    return jobs.internal_detail(job)
