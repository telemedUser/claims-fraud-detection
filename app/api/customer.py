"""Public customer journey: policy lookup, claim intake and status. Role: public."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app import jobs, ratelimit
from app.api.common import accept_submission, verified_policy
from app.api.customer_view import customer_view
from app.db.repos import DISEASES, open_repos

router = APIRouter(tags=["customer"])


class PolicyLookup(BaseModel):
    policy_number: str
    date_of_birth: date


@router.post("/api/policies/lookup")
async def lookup_policy(body: PolicyLookup, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    wait = ratelimit.lookup_limiter().acquire(
        [f"ip:{client_ip}", f"policy:{body.policy_number.strip().upper()}"])
    if wait is not None:
        raise HTTPException(429, "Too many lookup attempts. Please wait a moment and try again.",
                            headers={"Retry-After": str(ratelimit.retry_after_seconds(wait))})
    p = verified_policy(body.policy_number, body.date_of_birth)
    hospitals = []
    with open_repos() as repos:
        for hid in p["network_hospital_ids"]:
            h = repos.hospital(hid)
            doctors = [{"id": did, "name": d["name"], "specialty": d["specialty"], "qualification": d["qualification"]}
                       for did, d in repos.doctors_at(hid).items()]
            hospitals.append({"id": hid, "name": h["name"], "city": h["city"], "address": h["address"],
                              "specialties": h["specialties"], "doctors": doctors})
    covered = set(p["covered_disease_ids"])
    disease = lambda k: {"id": k, "name": DISEASES[k]["name"], "category": DISEASES[k]["category"]}  # noqa: E731
    return {"policy_number": body.policy_number.strip().upper(), "holder_name": p["holder_name"], "plan": p["plan"],
            "sum_insured": p["sum_insured"], "valid_from": p["valid_from"], "valid_to": p["valid_to"],
            "network_hospitals": hospitals,
            "covered_diseases": [disease(k) for k in p["covered_disease_ids"]],
            "not_covered": [disease(k) for k in DISEASES if k not in covered]}


@router.post("/api/claims", status_code=202)
async def submit_claim(payload: str = Form(..., description="ClaimSubmission as JSON"),
                       documents: list[UploadFile] = File(default=[]),
                       document_types: str = Form("[]", description="JSON list of doc types, same order as documents")):
    return {"claim_id": await accept_submission(payload, documents, document_types)}


@router.get("/api/claims/{claim_id}/status")
async def claim_status(claim_id: str):
    job = jobs.JOBS.get(claim_id)
    if not job:
        raise HTTPException(404, "Claim not found")
    return customer_view(job)
