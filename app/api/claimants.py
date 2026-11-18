"""Investigator view of user (claimant) profiles: every earlier claim, behaviour metrics and risk signals.

Staff only (all console roles). Each profile view is written to the audit log as ``claimant_access``.
Identity fields (name, date of birth) are shown to staff here and are never sent to the LLM.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app import jobs
from app.api.auth import CurrentUser
from app.api.deps import INVESTIGATE_ROLES, require_roles
from app.core.user_profile import build_profile, days_to_term_end
from app.db import audit
from app.db.repos import DISEASES, open_repos
from app.db.session import get_session

router = APIRouter(tags=["claimants"])
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _profile(repos, claimant_id: str, policy_number: str | None):
    records = repos.claimant_records(claimant_id)
    policy = repos.policy(policy_number) if policy_number else None
    profile = build_profile(records[-1] if records else None, records[:-1], policy)
    return records, policy, profile


@router.get("/api/internal/claimants", dependencies=[Depends(require_roles(*INVESTIGATE_ROLES))])
async def list_claimants(q: str | None = Query(None, max_length=80, description="Search claimant id, name or policy number")):
    term = (q or "").strip().lower()
    out = []
    with open_repos() as repos:
        for c in repos.claims.claimants():
            if term and term not in " ".join(str(v or "") for v in (c["claimant_id"], c["name"], c["policy_number"])).lower():
                continue
            records, policy, profile = _profile(repos, c["claimant_id"], c["policy_number"])
            top = max((SEVERITY_ORDER[s["severity"]] for s in profile["signals"]), default=None)
            out.append({**{k: c[k] for k in ("claimant_id", "name", "policy_number")},
                        "plan": (policy or {}).get("plan"), "claims": profile["metrics"]["claims"],
                        "total_claimed": profile["metrics"]["total_claimed"], "last_claim": profile["metrics"]["last_claim"],
                        "flagged_claims": profile["metrics"]["flagged_claims"], "signals": len(profile["signals"]),
                        "top_severity": None if top is None else next(k for k, v in SEVERITY_ORDER.items() if v == top)})
    return out


@router.get("/api/internal/claimants/{claimant_id}")
async def get_claimant(claimant_id: str, user: CurrentUser = Depends(require_roles(*INVESTIGATE_ROLES))):
    with open_repos() as repos:
        person = next((c for c in repos.claims.claimants() if c["claimant_id"] == claimant_id), None)
        if person is None:
            raise HTTPException(404, "Claimant not found")
        records, policy, profile = _profile(repos, claimant_id, person["policy_number"])
    with get_session() as s:
        audit.record(s, "claimant_access", actor_id=user.id, entity_type="claimant", entity_id=claimant_id)

    claims = []
    for r in records:
        job = jobs.JOBS.get(r["claim_id"])
        a = job.get("assessment") if job else None
        lag = (r["submitted"] - r["discharge"]).days if r.get("submitted") and r.get("discharge") else None
        claims.append({**r, "diagnosis": DISEASES.get(r.get("disease") or "", {}).get("name"),
                       "stay_days": (r["discharge"] - r["admission"]).days if r.get("admission") and r.get("discharge") else None,
                       "submission_lag_days": lag, "days_to_term_end": days_to_term_end(r.get("admission"), policy),
                       "risk_score": a.risk_score if a else None, "queue": a.decision if a else None,
                       "in_console": job is not None})
    return {"claimant": person,
            "policy": None if not policy else {k: policy.get(k) for k in
                                               ("plan", "sum_insured", "valid_from", "valid_to", "network_hospital_ids")},
            "metrics": profile["metrics"], "signals": profile["signals"], "claims": list(reversed(claims)),
            "config_version": profile["config_version"]}
