"""Background claim processing with per-stage progress, plus the customer and internal views of a job.

Jobs live in memory (demo). Use a queue + database (e.g. SQS + DynamoDB) in production.
"""
import asyncio
import threading
import time
from datetime import datetime, timezone

from app.db.repos import open_repos
from app.models import Claim, DocumentInfo
from app.pipeline import AGENT_NAMES, assess_claim

AGENT_STAGES = list(AGENT_NAMES)
STAGES = ["intake", *AGENT_STAGES, "scoring", "summary"]

# Customer-facing wording and views live in app/api/customer_view.py; re-exported for the internal views.
from app.api.customer_view import (  # noqa: E402,F401
    CUSTOMER_CHECKS, CUSTOMER_LABELS, NO_ISSUES_BELOW, OUTCOMES, SIMULATED_CHECKS, check_outcome, customer_report,
    customer_view,
)

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
        # Uploaded bytes, same order as "documents". Served only through the role-protected documents route
        # and never included in a view. Lives and dies with the in-memory job.
        "_files": [d.data for d in docs],
        # Latest human decision (approve / deny) recorded by an investigator, or None while pending.
        "review": None,
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


async def _process(job, claim, docs, use_llm, register="claim"):
    cb = _progress(job)
    cb("intake", "running", {"documents": len(docs)})
    cb("intake", "done", {"documents": len(docs), "bytes": sum(d.size for d in docs)})
    try:
        job["assessment"] = await assess_claim(claim, docs, use_llm, progress=cb, register=register)
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


async def run_sync(claim: Claim, docs: list[DocumentInfo], use_llm: bool = True, register: str | None = "claim") -> dict:
    job = _new_job(claim, docs, use_llm)
    await _process(job, claim, docs, use_llm, register)
    return job


def reset() -> None:
    JOBS.clear()


# ---------------------------------------------------------------- views

def internal_summary(job: dict) -> dict:
    claim: Claim = job["claim"]
    a = job["assessment"]
    with open_repos() as repos:
        hosp = repos.hospital(claim.hospital_id) or {}
    return {"claim_id": claim.claim_id, "status": job["status"], "submitted_at": job["submitted_at"],
            "policy_number": claim.policy_number, "claimant": claim.claimant_name,
            "hospital": hosp.get("name", claim.hospital_id), "diagnosis": claim.diagnosis,
            "claimed_amount": claim.claimed_amount, "use_llm": job["use_llm"],
            "risk_score": a.risk_score if a else None, "decision": a.decision if a else None,
            "duration_ms": a.orchestration.total_duration_ms if a else None,
            "review": job.get("review")}


def internal_detail(job: dict) -> dict:
    return {**internal_summary(job), "claim": job["claim"].model_dump(mode="json"), "documents": job["documents"],
            "stages": job["stages"], "events": job["events"], "error": job["error"],
            "finished_at": job["finished_at"],
            "assessment": job["assessment"].model_dump(mode="json") if job["assessment"] else None,
            "customer_view": customer_view(job)}
