"""Operational routes: health, console overview, reset, direct assessment."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError

from app import catalog, jobs, runtime_settings
from app.api.auth import CurrentUser
from app.api.common import enforce_policy_rules, read_documents
from app.api.deps import ADMIN_ROLES, ASSESS_ROLES, INVESTIGATE_ROLES, require_roles
from app.api.demo import DEMO_CASES
from app.db.repos import open_repos
from app.db.session import get_engine
from app.models import Claim, FraudAssessment
from app.seed import run as seed_run

router = APIRouter(tags=["internal"])


@router.get("/api/health", tags=["ops"])
async def health():
    return {"status": "ok"}


@router.get("/api/internal/overview", dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
async def internal_overview():
    return {**catalog.overview(), "claims_processed": len(jobs.JOBS)}


class LlmSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("/api/internal/settings", dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
async def internal_settings():
    """Server-side analysis settings shown in the console. Read by every console role."""
    return {"llm_analysis": runtime_settings.llm_switch()}


@router.post("/api/internal/settings/llm")
async def set_llm_analysis(body: LlmSwitchIn, user: CurrentUser = Depends(require_roles(*ADMIN_ROLES))):
    """Administrator only. Turns LLM analysis on or off for every claim submitted after the change (audited)."""
    return {"llm_analysis": runtime_settings.set_llm_switch(body.enabled, user.id)}


@router.post("/api/internal/reset", dependencies=[Depends(require_roles(*ADMIN_ROLES))])
async def internal_reset():
    try:
        seed_run.reset_database(get_engine())  # the seeded PDFs from start-up stay on disk
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    jobs.reset()
    DEMO_CASES.clear()
    return {"status": "reset"}


@router.post("/api/assess", response_model=FraudAssessment, dependencies=[Depends(require_roles(*ASSESS_ROLES))])
async def assess(claim: str = Form(..., description="Claim as JSON"),
                 documents: list[UploadFile] = File(default=[]),
                 document_types: str = Form("[]"),
                 use_llm: bool = Form(True),
                 test_mode: bool = Query(False, description="Skip policy checks and record the claim in history labelled is_test")):
    """Investigator, Fraud_Team or Administrator only. History is written only in test mode."""
    try:
        parsed = Claim.model_validate(json.loads(claim))
        types = json.loads(document_types)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, f"Invalid claim: {e}")
    if not test_mode:
        with open_repos() as repos:
            p = repos.policy((parsed.policy_number or "").strip().upper())
        if not p:
            raise HTTPException(404, "Unknown policy number.")
        if p["claimant_id"] != parsed.claimant_id:
            raise HTTPException(422, "Claimant does not match the policy holder.")
        if not parsed.disease_id:
            raise HTTPException(422, "disease_id is required.")
        enforce_policy_rules(p, parsed)
    docs = await read_documents(documents, types if isinstance(types, list) else [])
    # use_llm can only turn the LLM off for this staff request; the server switch decides whether it can be on.
    job = await jobs.run_sync(parsed, docs, use_llm and runtime_settings.llm_effective(),
                              register="test" if test_mode else None)
    if job["status"] != "completed":
        raise HTTPException(500, "Assessment failed")
    return job["assessment"]
