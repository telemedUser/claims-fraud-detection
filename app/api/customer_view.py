"""What the policyholder sees (Requirement 8.3 to 8.5). Role: public.

Rules for everything in this module:
  * Check results use only three labels: "No issues found", "Specialist review", "SIMULATED"
    (codes ``no_issues``, ``unavailable``, ``simulated``).
  * Outcome text says the claim was *received*. It never says a claim was verified, genuine or authentic,
    and never discloses findings, scores, routing bands or internal agent names. It says "approved" or
    "not approved" only after an investigator records that decision (``HUMAN_OUTCOMES``); automated
    checks alone never approve or reject.
  * Check labels are customer wording (``CUSTOMER_CHECKS``), not agent identifiers.

``app.jobs`` re-exports these names so the internal views keep working.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

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


# ---------------------------------------------------------------- next step, timeline and insights
# Contact details are placeholders for the demo; set them in the environment for a real deployment.
HELPLINE = {"number": os.getenv("HELPLINE_NUMBER", "1800-000-0000"),
            "hours": os.getenv("HELPLINE_HOURS", "Mon to Fri, 8 am to 6 pm"),
            "email": os.getenv("HELPLINE_EMAIL", "claims.support@example.com")}
REQUIRED_DOCS = [("medical_bill", "Itemised medical bill", True), ("medical_report", "Medical report or discharge summary", True),
                 ("prescription", "Prescription", False), ("lab_report", "Lab report", False),
                 ("payment_receipt", "Payment receipt", False)]
# Only objective, fixable problems with the files themselves reach the customer: nothing about what a check
# looked for or why. code -> (document type or None, message).
RESUBMIT_REASONS = {
    "NO_DOCUMENTS": (None, "No documents were attached to this claim."),
    "MISSING_MEDICAL_BILL": ("medical_bill", "We did not receive an itemised bill."),
    "MISSING_MEDICAL_REPORT": ("medical_report", "We did not receive a medical report or discharge summary."),
    "UNEXPECTED_FILE_TYPE": ("file", "This file type is not supported. Please upload a PDF, JPG or PNG."),
    "PDF_UNREADABLE": ("file", "We could not open this file. Please upload a clearer or complete copy."),
    "IMAGE_UNREADABLE": ("file", "We could not open this image. Please upload a clearer copy."),
    "MEDICAL_DOCS_NOT_READABLE": ("medical", "We could not read the text in your medical documents. Please upload clear, text-based copies."),
}
LEVELS = {"approved": "green", "under_review": "amber", "verification": "red"}
FOLLOW_UP_DAYS = {"approved": 0, "under_review": 2, "verification": 5}


def _add_working_days(start: date, n: int) -> date:
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def resubmit_items(a, documents: list[dict]) -> list[dict]:
    """Objective file problems the customer can fix by uploading again. Never reveals what other checks saw."""
    items: list[dict] = []
    seen: set[tuple] = set()
    names = {d["filename"] for d in documents}
    for r in a.agent_results:
        for f in r.findings:
            if f.source != "rule" or f.code not in RESUBMIT_REASONS:
                continue
            kind, message = RESUBMIT_REASONS[f.code]
            fname = f.detail.split(":", 1)[0] if kind == "file" and ":" in f.detail else None
            key = (f.code, fname if fname in names else None)
            if key in seen:
                continue
            seen.add(key)
            items.append({"kind": kind or "all", "label": fname if fname in names else
                          dict((k, v) for k, v, _ in REQUIRED_DOCS).get(kind, "Supporting documents"),
                          "reason": message})
    return items


def next_step(outcome_code: str, items: list[dict], claim_id: str) -> dict:
    """What the customer should do now: nothing, wait, upload again, or call the helpline."""
    helpline = {**HELPLINE, "reference": claim_id}
    if items:
        return {"type": "resubmit", "level": "red" if outcome_code == "verification" else "amber",
                "title": "Please upload your documents again",
                "detail": "Some files could not be used. Upload clear copies of the documents below and quote your claim "
                          "reference. If you need help, call us.",
                "documents": items, "helpline": helpline}
    if outcome_code == "verification":
        return {"type": "call_helpline", "level": "red", "title": "Please call our helpline",
                "detail": "Your claim needs a short conversation with our team before it can move forward. You do not need "
                          "to upload anything now. Call within 5 working days and quote your claim reference.",
                "documents": [], "helpline": helpline}
    if outcome_code == "under_review":
        return {"type": "wait", "level": "amber", "title": "No action needed right now",
                "detail": "A claims specialist is looking at your claim. We will contact you if we need anything else. "
                          "Keep your original bills and reports safe.",
                "documents": [], "helpline": helpline}
    return {"type": "none", "level": "green", "title": "Nothing to do for now",
            "detail": "Your claim is being processed. We will update you by email and SMS.",
            "documents": [], "helpline": helpline}


def timeline(outcome_code: str, submitted: datetime | None, completed: datetime | None) -> list[dict]:
    start = (submitted or datetime.now()).date()
    follow = FOLLOW_UP_DAYS[outcome_code]
    steps = [{"key": "received", "label": "Claim received", "detail": "Your claim and documents are with us.",
              "date": start.isoformat(), "state": "done"},
             {"key": "checked", "label": "Automatic checks complete", "detail": "Five quick checks on your claim.",
              "date": (completed or submitted or datetime.now()).date().isoformat(), "state": "done"}]
    if outcome_code == "approved":
        steps.append({"key": "processing", "label": "Processing", "detail": "Settlement details will be sent to you.",
                      "date": None, "state": "current"})
        steps.append({"key": "update", "label": "Update by email and SMS", "detail": "", "date": None, "state": "upcoming"})
    else:
        who = "A claims specialist reviews" if outcome_code == "under_review" else "Our team contacts you about"
        steps.append({"key": "review", "label": "Specialist step", "detail": f"{who} your claim.",
                      "date": _add_working_days(start, follow).isoformat(), "state": "current",
                      "expected": f"by {follow} working days"})
        steps.append({"key": "update", "label": "Update by email and SMS", "detail": "", "date": None, "state": "upcoming"})
    return steps


def insights(claim: Claim, pol: dict | None, documents: list[dict]) -> dict:
    """Facts from the customer's own submission, shown on the insights page. Nothing from the checks."""
    days = max(1, (claim.discharge_date - claim.admission_date).days)
    total = sum(max(li.amount, 0) for li in claim.invoice.line_items) or claim.invoice.total or 1
    items = sorted(({"description": li.description, "amount": li.amount, "share": round(100 * li.amount / total, 1)}
                    for li in claim.invoice.line_items), key=lambda x: -x["amount"])
    sum_insured = (pol or {}).get("sum_insured")
    got = {d["doc_type"] for d in documents}
    # Plain arithmetic on what the customer typed and uploaded: claimed amount vs. bill, and bill total vs. its items.
    items_sum = sum(li.amount for li in claim.invoice.line_items)
    return {
        "amounts": {"claimed": claim.claimed_amount, "bill_total": claim.invoice.total, "items_sum": items_sum,
                    "claim_vs_bill": round(claim.claimed_amount - claim.invoice.total, 2),
                    "bill_vs_items": round(claim.invoice.total - items_sum, 2)},
        "stay": {"days": days, "per_day": round(claim.claimed_amount / days)},
        "coverage": {"plan": (pol or {}).get("plan"), "sum_insured": sum_insured,
                     "claimed_pct": round(100 * claim.claimed_amount / sum_insured, 1) if sum_insured else None,
                     "valid_to": (pol or {}).get("valid_to")},
        "bill": {"invoice_number": claim.invoice.invoice_number, "invoice_date": claim.invoice.invoice_date.isoformat(),
                 "total": claim.invoice.total, "items": items},
        "checklist": [{"doc_type": k, "label": label, "required": req, "received": k in got} for k, label, req in REQUIRED_DOCS],
        "tips": ["Keep original bills, prescriptions and reports until the claim is settled.",
                 "Quote your claim reference whenever you contact us.",
                 "Clear, complete PDF or photo copies are processed faster.",
                 "Make sure the bill shows the hospital name, bill number, date and itemised charges."],
    }


# Decisions recorded by an investigator (app/api/decisions.py). Only these two change the customer's outcome;
# the reason the investigator typed stays internal.
HUMAN_OUTCOMES = {
    "approve": {"code": "approved", "title": "Claim approved",
                "message": "A claims specialist has reviewed and approved your claim. Settlement details will be sent to you by email and SMS.",
                "next_steps": ["Settlement details will be sent to you by email and SMS."]},
    "deny": {"code": "verification", "title": "Claim not approved",
             "message": "A claims specialist has reviewed your claim and could not approve it. Please call our helpline for the details and your options.",
             "next_steps": ["Call our helpline and quote your claim reference."]},
}


def human_decision(review: dict, claim_id: str, steps: list[dict]) -> tuple[dict, str, dict, list[dict]]:
    approved = review["decision"] == "approve"
    outcome = HUMAN_OUTCOMES[review["decision"]]
    helpline = {**HELPLINE, "reference": claim_id}
    step = ({"type": "none", "level": "green", "title": "Nothing to do",
             "detail": "Your claim has been approved. We will send settlement details by email and SMS.",
             "documents": [], "helpline": helpline} if approved else
            {"type": "call_helpline", "level": "red", "title": "Please call our helpline",
             "detail": "A specialist could not approve your claim. Call us to hear why and what you can do next. "
                       "Quote your claim reference.", "documents": [], "helpline": helpline})
    decided = (_parse(review.get("at")) or datetime.now()).date().isoformat()
    steps = [s for s in steps if s["state"] == "done"] + [
        {"key": "decided", "label": "Claim approved" if approved else "Claim not approved",
         "detail": "Reviewed by a claims specialist.", "date": decided, "state": "done"},
        {"key": "update", "label": "Settlement details sent" if approved else "Call our helpline",
         "detail": "", "date": None, "state": "current"},
    ]
    return outcome, "green" if approved else "red", step, steps


def customer_report(job: dict) -> dict:
    claim: Claim = job["claim"]
    a = job["assessment"]
    with open_repos() as repos:
        pol = repos.policy(claim.policy_number) if claim.policy_number else None
        hosp = repos.hospital(claim.hospital_id) or {}
        doc = repos.doctor(claim.doctor_id) or {}
    outcome = OUTCOMES[a.decision]
    documents = [{"filename": d["filename"], "doc_type": d["doc_type"]} for d in job["documents"]]
    items = resubmit_items(a, documents)
    step = next_step(outcome["code"], items, claim.claim_id)
    level = step["level"] if step["level"] != "green" else LEVELS[outcome["code"]]
    steps = timeline(outcome["code"], _parse(job["submitted_at"]), _parse(job["finished_at"]))
    review = job.get("review")
    if review and review["decision"] in HUMAN_OUTCOMES:
        # A person has decided. This is the only case where the customer sees "approved" or "not approved".
        outcome, level, step, steps = human_decision(review, claim.claim_id, steps)
    return {
        "outcome": outcome,
        "level": level,
        "next_step": step,
        "timeline": steps,
        "insights_url": f"/claims/{claim.claim_id}/insights",
        "insights": insights(claim, pol, documents),
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
        "documents": documents,
    }