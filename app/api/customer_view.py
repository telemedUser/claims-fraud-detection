"""What the policyholder sees (Requirement 8.3 to 8.5). Role: public.

Rules for everything in this module:
  * Check results use only three labels: "No issues found", "Verification unavailable", "SIMULATED"
    (codes ``no_issues``, ``unavailable``, ``simulated``).
  * Outcome text says the claim was *received*. It never says a claim was approved, verified, genuine or
    authentic, and never discloses findings, scores, routing bands or internal agent names.
  * Check labels are customer wording (``CUSTOMER_CHECKS``), not agent identifiers.

``app.jobs`` re-exports these names so the internal views keep working.
"""
from __future__ import annotations

from app.db.repos import open_repos
from app.models import Claim

# Keys are internal stage keys and are never shown; only the values are. Order is the display order.
CUSTOMER_LABELS = {
    "intake": "Documents received",
    "provider_profile": "Checking hospital and doctor",
    "claimant_profile": "Checking policy and claim history",
    "document_scan": "Checking your documents",
    "invoice_check": "Validating your medical bill",
    "medical_review": "Reviewing your medical records",
    "scoring": "Assessing your claim",
    "summary": "Preparing your claim report",
}
CUSTOMER_STAGE_KEYS = {s: ("intake" if s == "intake" else f"step_{i}") for i, s in enumerate(CUSTOMER_LABELS)}
CUSTOMER_CHECKS = {
    "provider_profile": "Hospital and doctor check",
    "claimant_profile": "Policy and claim history",
    "document_scan": "Document review",
    "invoice_check": "Medical bill validation",
    "medical_review": "Medical records review",
}
OUTCOMES = {
    "auto_approve": {"code": "approved", "title": "Claim received",
                     "message": "We have received your claim and it is being processed. Any settlement will be communicated to you once processing is complete.",
                     "next_steps": ["We will notify you of the outcome once processing is complete.",
                                    "You will receive updates by email and SMS."]},
    "manual_review": {"code": "under_review", "title": "Claim received and under review",
                      "message": "A claims specialist will review a few details of your claim.",
                      "next_steps": ["We will contact you within 2 working days if we need anything else.",
                                     "Keep your original bills and reports until the claim is settled."]},
    "investigate": {"code": "verification", "title": "Claim received, more information may be needed",
                    "message": "We have received your claim. It needs additional review before it can be processed.",
                    "next_steps": ["Our verification team will contact you within 5 working days.",
                                   "Please keep the original documents and hospital contact details ready."]},
}
FAILED_MESSAGE = "We couldn't finish processing your claim automatically. Our team will review it manually."
NO_ISSUES_BELOW = 30  # per-check score below which the customer sees "No issues found"
# Checks backed by simulated (fictional) registries are always labelled SIMULATED.
SIMULATED_CHECKS = {"provider_profile"}


def check_outcome(agent: str, score: float) -> str:
    """Customer-safe label code for one check. The score itself is never returned."""
    if agent in SIMULATED_CHECKS:
        return "simulated"
    return "no_issues" if score < NO_ISSUES_BELOW else "unavailable"


def customer_view(job: dict) -> dict:
    # The stage key is opaque (position-based) so internal agent and stage names never reach the customer.
    stages = [{"key": CUSTOMER_STAGE_KEYS[s], "label": CUSTOMER_LABELS[s], "status": job["stages"][s]["status"],
               "ai_review": job["stages"][s]["detail"] == "llm_review"}
              for s in CUSTOMER_LABELS if s in job["stages"]]
    out = {"claim_id": job["claim_id"], "status": job["status"], "submitted_at": job["submitted_at"], "stages": stages}
    if job["status"] == "completed":
        out["report"] = customer_report(job)
    if job["status"] == "failed":
        out["message"] = FAILED_MESSAGE
    return out


def customer_report(job: dict) -> dict:
    claim: Claim = job["claim"]
    a = job["assessment"]
    with open_repos() as repos:
        pol = repos.policy(claim.policy_number) if claim.policy_number else None
        hosp = repos.hospital(claim.hospital_id) or {}
        doc = repos.doctor(claim.doctor_id) or {}
    return {
        "outcome": OUTCOMES[a.decision],
        "checks": [{"label": CUSTOMER_CHECKS[r.agent],
                    "outcome": check_outcome(r.agent, r.score)} for r in a.agent_results],
        "claim": {
            "claim_id": claim.claim_id, "policy_number": claim.policy_number, "plan": pol and pol["plan"],
            "policyholder": claim.claimant_name, "hospital": hosp.get("name"), "hospital_city": hosp.get("city"),
            "doctor": doc.get("name"), "diagnosis": claim.diagnosis,
            "admission_date": claim.admission_date.isoformat(), "discharge_date": claim.discharge_date.isoformat(),
            "claimed_amount": claim.claimed_amount, "invoice_number": claim.invoice.invoice_number,
            "submitted_at": job["submitted_at"], "completed_at": job["finished_at"],
        },
        "documents": [{"filename": d["filename"], "doc_type": d["doc_type"]} for d in job["documents"]],
    }
