import asyncio
import time

from app import llm, llm_review
from app.agents.claimant_profile import ClaimantProfileAgent
from app.agents.document_scan import DocumentScanAgent
from app.agents.invoice_check import InvoiceCheckAgent
from app.agents.provider_profile import ProviderProfileAgent
from app.data import store
from app.models import (AgentResult, AgentTrace, Claim, DocumentInfo, Finding, FraudAssessment,
                        Orchestration)

AGENTS = [ProviderProfileAgent(), ClaimantProfileAgent(), DocumentScanAgent(), InvoiceCheckAgent()]
WEIGHTS = {"provider_profile": 0.30, "claimant_profile": 0.20, "document_scan": 0.25, "invoice_check": 0.25}
REVIEW_AT, INVESTIGATE_AT = 30, 60
PEAK_FACTOR = 0.8


def _decide(score: float) -> str:
    if score >= INVESTIGATE_AT:
        return "investigate"
    if score >= REVIEW_AT:
        return "manual_review"
    return "auto_approve"


def _noop(stage: str, status: str, info: dict | None = None) -> None:
    pass


async def _run(agent, claim, docs, t0, use_llm, progress):
    def work():
        # Each agent runs in its own thread with its own event loop, so CPU-bound or blocking
        # work (PDF parsing, OCR, LLM calls) in one agent cannot hold up the others.
        start = time.perf_counter()
        progress(agent.name, "rules")
        try:
            result = asyncio.run(agent.analyze(claim, docs))
            progress(agent.name, "rules_done", {"rule_score": result.score, "findings": len(result.findings)})
            if use_llm:
                if llm.enabled():
                    progress(agent.name, "llm_review")
                result = llm_review.review(agent.name, claim, docs, result)
            else:
                result.rule_score = result.score
                result.reasoning = "LLM review turned off for this request; rule-based result only."
        except Exception as e:  # one failing agent must not sink the claim
            result = AgentResult(agent=agent.name, score=50, findings=[
                Finding(code="AGENT_ERROR", severity="medium", detail=f"{agent.name} failed: {e}")])
        progress(agent.name, "done", {"score": result.score, "llm_used": result.llm_used})
        return result, (start - t0) * 1000, (time.perf_counter() - start) * 1000

    return await asyncio.to_thread(work)


def _overlapped(traces) -> bool:
    """True if any agent started before another one finished."""
    return any(a.started_at_ms < b.started_at_ms + b.duration_ms and b is not a
               for a in traces for b in traces if b.started_at_ms <= a.started_at_ms)


async def assess_claim(claim: Claim, docs: list[DocumentInfo], use_llm: bool = True,
                       progress=_noop) -> FraudAssessment:
    """progress(stage, status, info) is called as agents move through: rules -> rules_done ->
    llm_review -> done, then for the 'scoring' and 'summary' stages. It may be called from worker threads."""
    t0 = time.perf_counter()
    runs = await asyncio.gather(*(_run(a, claim, docs, t0, use_llm, progress) for a in AGENTS))
    total_ms = (time.perf_counter() - t0) * 1000
    results = [r for r, _, _ in runs]
    progress("scoring", "running")

    weighted = sum(WEIGHTS[r.agent] * r.score for r in results)
    peak_r = max(results, key=lambda r: r.score)
    floor = PEAK_FACTOR * peak_r.score
    # A single very bad signal (e.g. duplicate invoice, invalid license) must not be diluted by averaging.
    score = round(min(100.0, max(weighted, floor)), 1)
    decision = _decide(score)

    if floor > weighted:
        reason = (f"Score set by the peak rule: {PEAK_FACTOR} x {peak_r.agent} ({peak_r.score:.0f}) = {floor:.1f} "
                  f"is higher than the weighted average {weighted:.1f}.")
    else:
        reason = f"Score set by the weighted average ({weighted:.1f}); the peak rule ({floor:.1f}) was lower."
    reason += f" {score} maps to '{decision}'."

    traces = [AgentTrace(agent=r.agent, weight=WEIGHTS[r.agent], score=r.score,
                         weighted_contribution=round(WEIGHTS[r.agent] * r.score, 2),
                         started_at_ms=round(s, 2), duration_ms=round(d, 2), finding_count=len(r.findings))
              for r, s, d in runs]
    orchestration = Orchestration(
        agents_run_in_parallel=_overlapped(traces), total_duration_ms=round(total_ms, 2),
        sum_of_agent_durations_ms=round(sum(t.duration_ms for t in traces), 2), traces=traces,
        weighted_score=round(weighted, 2), peak_agent=peak_r.agent, peak_score=peak_r.score,
        peak_floor=round(floor, 2), final_score=score,
        score_rule=f"final = min(100, max(sum(weight x agent score), {PEAK_FACTOR} x highest agent score))",
        thresholds={"manual_review_at": REVIEW_AT, "investigate_at": INVESTIGATE_AT},
        decision_reason=reason)

    progress("scoring", "done", {"score": score, "decision": decision})

    progress("summary", "running")
    summary = await llm.summarize(claim.claim_id, score, decision, results, use_llm)
    progress("summary", "done")
    store.register_claim(claim, [d.sha256 for d in docs])
    return FraudAssessment(claim_id=claim.claim_id, risk_score=score, decision=decision,
                           agent_results=results, orchestration=orchestration, summary=summary)
