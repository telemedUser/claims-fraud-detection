"""Background claim processing with per-stage progress, plus the customer and internal views of a job.

Jobs live in memory (demo). Use a queue + database (e.g. SQS + DynamoDB) in production.
"""
import asyncio
import threading
import time
from datetime import datetime, timezone

from app.data import store
from app.models import Claim, DocumentInfo
from app.orchestrator import AGENTS, assess_claim

AGENT_STAGES = [a.name for a in AGENTS]
STAGES = ["intake", *AGENT_STAGES, "scoring", "summary"]

# Customer-facing wording. Internal agent names and scores are never shown to the customer.
CUSTOMER_LABELS = {
    "intake": "Documents received",
    "provider_profile": "Verifying hospital and doctor",
    "claimant_profile": "Checking policy and claim history",
    "document_scan": "Checking document authenticity",
    "invoice_check": "Validating your medical bill",
    "scoring": "Assessing your claim",
    "summary": "Preparing your claim report",
}
CUSTOMER_CHECKS = {
    "provider_profile": "Hospital and doctor verification",
    "claimant_profile": "Policy and claim history",
    "document_scan": "Document authenticity",
    "invoice_check": "Medical bill validation",
}
OUTCOMES = {
    "auto_approve": {"code": "approved", "title": "Claim approved for settlement",
                     "message": "Your claim passed all automated checks. Settlement is usually completed within 3 working days.",
                     "next_steps": ["We will transfer the approved amount to your registered bank account.",
                                    "You will receive a confirmation by email and SMS."]},
    "manual_review": {"code": "under_review", "title": "Claim under review",
                      "message": "A claims specialist will review a few details of your claim.",
                      "next_steps": ["We will contact you within 2 working days if we need anything else.",
                                     "Keep your original bills and reports until the claim is settled."]},
    "investigate": {"code": "verification", "title": "Additional verification required",
                    "message": "Your claim needs further verification before it can be processed.",
                    "next_steps": ["Our verification team will contact you within 5 working days.",
                                   "Please keep the original documents and hospital contact details ready."]},
}
VERIFIED_BELOW = 30  # per-check score below which the customer sees "Verified"

JOBS: dict[str, dict] = {}
_TASKS: set[asyncio.Task] = set()
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job(claim: Claim, docs: list[DocumentInfo], use_llm: bool) -> dict:
    job = {
        "claim_id": claim.claim_id, "status": "processing", "submitted_at": _now(), "finished_at": None,
        "use_llm": use_llm, "claim": claim,
        "documents": [{"filename": d.filename, "doc_type": d.doc_type, "content_type": d.content_type, "size": d.size}
                      for d in docs],
        "stages": {s: {"status": "pending", "detail": None, "started_ms": None, "finished_ms": None} for s in STAGES},
        "events": [], "assessment": None, "error": None, "_t0": time.perf_counter(),
    }
    JOBS[claim.claim_id] = job
    return job


def _progress(job):
    def cb(stage: str, status: str, info: dict | None = None):
        ms = round((time.perf_counter() - job["_t0"]) * 1000, 1)
        with _LOCK:
            st = job["stages"][stage]
            if st["started_ms"] is None:
                st["started_ms"] = ms
            st["status"] = "done" if status == "done" else "running"
            st["detail"] = status
            if status == "done":
                st["finished_ms"] = ms
            job["events"].append({"t_ms": ms, "stage": stage, "status": status, "info": info or {}})
    return cb


async def _process(job, claim, docs, use_llm):
    cb = _progress(job)
    cb("intake", "running", {"documents": len(docs)})
    cb("intake", "done", {"documents": len(docs), "bytes": sum(d.size for d in docs)})
    try:
        job["assessment"] = await assess_claim(claim, docs, use_llm, progress=cb)
        job["status"] = "completed"
    except Exception as e:  # surfaced to the customer as a generic failure, detail kept internal
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
    job["finished_at"] = _now()


def start(claim: Claim, docs: list[DocumentInfo], use_llm: bool = True) -> dict:
    job = _new_job(claim, docs, use_llm)
    task = asyncio.create_task(_process(job, claim, docs, use_llm))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return job


async def run_sync(claim: Claim, docs: list[DocumentInfo], use_llm: bool = True) -> dict:
    job = _new_job(claim, docs, use_llm)
    await _process(job, claim, docs, use_llm)
    return job


def reset() -> None:
    JOBS.clear()


# ---------------------------------------------------------------- views

def customer_view(job: dict) -> dict:
    stages = [{"key": s, "label": CUSTOMER_LABELS[s], "status": job["stages"][s]["status"],
               "ai_review": job["stages"][s]["detail"] == "llm_review"} for s in STAGES]
    out = {"claim_id": job["claim_id"], "status": job["status"], "submitted_at": job["submitted_at"], "stages": stages}
    if job["status"] == "completed":
        out["report"] = customer_report(job)
    if job["status"] == "failed":
        out["message"] = "We couldn't finish processing your claim automatically. Our team will review it manually."
    return out


def customer_report(job: dict) -> dict:
    claim: Claim = job["claim"]
    a = job["assessment"]
    pol = store.policy(claim.policy_number) if claim.policy_number else None
    hosp = store.hospital(claim.hospital_id) or {}
    doc = store.doctor(claim.doctor_id) or {}
    return {
        "outcome": OUTCOMES[a.decision],
        "checks": [{"label": CUSTOMER_CHECKS[r.agent],
                    "outcome": "verified" if r.score < VERIFIED_BELOW else "needs_review"} for r in a.agent_results],
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


def internal_summary(job: dict) -> dict:
    claim: Claim = job["claim"]
    a = job["assessment"]
    hosp = store.hospital(claim.hospital_id) or {}
    return {"claim_id": claim.claim_id, "status": job["status"], "submitted_at": job["submitted_at"],
            "policy_number": claim.policy_number, "claimant": claim.claimant_name,
            "hospital": hosp.get("name", claim.hospital_id), "diagnosis": claim.diagnosis,
            "claimed_amount": claim.claimed_amount, "use_llm": job["use_llm"],
            "risk_score": a.risk_score if a else None, "decision": a.decision if a else None,
            "duration_ms": a.orchestration.total_duration_ms if a else None}


def internal_detail(job: dict) -> dict:
    return {**internal_summary(job), "claim": job["claim"].model_dump(mode="json"), "documents": job["documents"],
            "stages": job["stages"], "events": job["events"], "error": job["error"],
            "finished_at": job["finished_at"],
            "assessment": job["assessment"].model_dump(mode="json") if job["assessment"] else None,
            "customer_view": customer_view(job)}
