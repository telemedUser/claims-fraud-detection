"""Claim assessment pipeline used by the API and jobs.

Runs the four legacy agents through the core orchestrator (``app.core.orchestrator.assess``),
then builds the ``FraudAssessment`` response the frontend reads. Scoring is the additive,
config-driven score from ``app.core.scoring`` over rule findings. When the console's LLM analysis switch is on
(``app.runtime_settings``), each agent then gets an LLM review (``app.llm_review``) that adds unscored AI
observations, and the LLM writes the investigator summary.

``decision`` is kept in the response for frontend compatibility. It is a routing
recommendation (queue), not an approval or a denial. The ``auto_approve`` key is interim:
it means the low-risk queue and is labelled "Low risk" in the UI.
"""
from __future__ import annotations

import asyncio
import time
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from app import llm, llm_review
from app.agents.claimant_profile import ClaimantProfileAgent
from app.agents.document_scan import DocumentScanAgent
from app.agents.invoice_check import InvoiceCheckAgent
from app.agents.medical_review import MedicalReviewAgent
from app.agents.provider_profile import ProviderProfileAgent
from app.core.legacy_adapter import adapt_findings, context_from_claim
from app.core.orchestrator import AssessmentContext, LegacyAgentRunner, _status_for, assess
from app.core.routing import route
from app.core.risk_config import load_risk_config
from app.db.repos import DEMO_CHANNEL, open_repos
from app.models import (AgentResult, AgentTrace, Claim, DocumentInfo, Finding, FraudAssessment,
                        Orchestration)

AGENTS = [ProviderProfileAgent(), ClaimantProfileAgent(), DocumentScanAgent(), InvoiceCheckAgent(), MedicalReviewAgent()]
AGENT_NAMES = [a.name for a in AGENTS]

# Interim mapping from the routing queue to the key the frontend already understands.
QUEUE_TO_DECISION = {"low": "auto_approve", "manual_review": "manual_review", "investigate": "investigate"}
AGENT_FAILURE_SCORE = 50  # shown for an agent that did not complete (customer sees "unavailable")


def _noop(stage: str, status: str, info: dict | None = None) -> None:
    pass


class _TrackedRunner(LegacyAgentRunner):
    """LegacyAgentRunner that emits progress and remembers what the legacy agent returned."""

    def __init__(self, legacy, t0: float, progress):
        super().__init__(legacy)
        self._t0 = t0
        self._progress = progress
        self.legacy_findings: list[Finding] | None = None
        self.check_ids: set[str] = set()
        self.started_ms = 0.0
        self.duration_ms = 0.0

    def run(self, ctx: AssessmentContext):
        start = time.perf_counter()
        self.started_ms = (start - self._t0) * 1000
        self._progress(self.name, "rules")
        try:
            result = asyncio.run(self.legacy.analyze(ctx.claim, list(ctx.documents)))
            drafts = adapt_findings(result.findings, context_from_claim(ctx.claim, list(ctx.documents), self.name))
        except Exception:
            self.duration_ms = (time.perf_counter() - start) * 1000
            raise
        self.legacy_findings = list(result.findings)
        self.check_ids = {d.check_id for d in drafts}
        self.duration_ms = (time.perf_counter() - start) * 1000
        self._progress(self.name, "rules_done", {"findings": len(drafts)})
        return drafts


def _overlapped(traces: list[AgentTrace]) -> bool:
    return any(a.started_at_ms < b.started_at_ms + b.duration_ms and b is not a
               for a in traces for b in traces if b.started_at_ms <= a.started_at_ms)


def claim_uuid(claim_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"claim:{claim_id}")


def _weighted_rule_score(runners, traces: list[AgentTrace], points_by_check: dict[str, float], config) -> float:
    """Rule score with each agent's fixed priority (risk_scoring.v1.yaml ``agent_weights``).

    An agent's rule score (its de-duplicated rule points, at most 100) is multiplied by its weight x the number
    of agents, so equal weights give the plain sum. Points from checks no agent owns (an orchestrator
    failure) count unweighted. Each trace records the agent's fixed weight and its weighted points."""
    n = len(runners)
    owned: set[str] = set()
    total = 0.0
    by_agent = {}
    for r in runners:
        owned |= set(r.check_ids)
        agent_points = min(100.0, sum(points_by_check.get(c, 0.0) for c in r.check_ids))  # the agent's rule score
        by_agent[r.name] = agent_points * config.agent_multiplier(r.name, n)
        total += by_agent[r.name]
    total += sum(p for c, p in points_by_check.items() if c not in owned)
    for t in traces:
        pct = config.agent_weights.get(t.agent, 100 / n) if config.agent_weights else 100 / n
        t.weightage_pct = round(pct, 1)
        t.weight = round(pct / 100, 4)
        t.weighted_contribution = round(by_agent.get(t.agent, 0.0), 1)
    return min(100.0, round(total, 1))


async def assess_claim(claim: Claim, docs: list[DocumentInfo], use_llm: bool = True,
                       progress=_noop, register: str | None = "claim") -> FraudAssessment:
    """progress(stage, status, info) is called per agent (rules, rules_done, done) and for the
    'scoring' and 'summary' stages. It may be called from worker threads.

    register: "claim" = write to history, "test" = write labelled is_test, "demo" = store it but keep it out of
    the history later claims are compared with (one-click demo scenarios), None = do not write.
    """
    t0 = time.perf_counter()
    config = load_risk_config()
    runners = [_TrackedRunner(a, t0, progress) for a in AGENTS]
    ctx = AssessmentContext(claim_id=claim_uuid(claim.claim_id), run_id=uuid4(),
                            rule_version=config.version, claim=claim, documents=tuple(docs))
    result = await assess(ctx, runners, config)
    total_ms = (time.perf_counter() - t0) * 1000

    points_by_check: dict[str, float] = {}
    for c in result.score.contributions:
        points_by_check[c.check_id] = points_by_check.get(c.check_id, 0.0) + c.points
    failed = {e.agent for e in result.executions if e.state != "SUCCEEDED"}

    results: list[AgentResult] = []
    traces: list[AgentTrace] = []
    completed: set[str] = set()
    for r in runners:
        if r.legacy_findings is None or r.name in failed and not r.check_ids:
            findings = [Finding(code="AGENT_ERROR", severity="medium", detail=f"{r.name} did not complete")]
            agent_score = float(AGENT_FAILURE_SCORE)
        else:
            findings = r.legacy_findings
            agent_score = min(100.0, round(sum(points_by_check.get(c, 0.0) for c in r.check_ids), 1))
            completed.add(r.name)
        results.append(AgentResult(agent=r.name, score=agent_score, findings=findings, rule_score=agent_score,
                                   reasoning="Rule-based result." if use_llm else "LLM analysis is off; rule-based result."))
        traces.append(AgentTrace(agent=r.name, weight=1.0, score=agent_score, weighted_contribution=agent_score,
                                 started_at_ms=round(r.started_ms, 2), duration_ms=round(r.duration_ms, 2),
                                 finding_count=len(findings)))

    # LLM review (console switch on): every completed agent in parallel. The review adds AI observations and
    # reasoning; llm_score then adds capped points for them on top of the rule score (risk_scoring.v1.yaml: llm).
    # Each agent is reported done as soon as its own review returns, so the timeline shows real per-agent times.
    async def _review(res: AgentResult) -> AgentResult:
        if use_llm and llm.enabled() and res.agent in completed:
            progress(res.agent, "llm_review")
            res = await asyncio.to_thread(llm_review.review, res.agent, claim, list(docs), res)
        progress(res.agent, "done", {"score": res.score, "llm_used": res.llm_used})
        return res

    results = list(await asyncio.gather(*(_review(res) for res in results)))
    progress("scoring", "running")

    rule_final = _weighted_rule_score(runners, traces, points_by_check, config)
    llm_extra = llm_review.llm_score(results, config) if use_llm else 0.0
    final = min(100.0, round(rule_final + llm_extra, 1))
    queue = route(final, config.bands)
    # Auto-approval is only for small claims: a low-risk claim at or above the limit goes to a person.
    limit = config.auto_approve_max_amount
    over_limit = queue == "low" and limit is not None and claim.claimed_amount >= limit
    needs_review = (result.needs_human_review and queue == "low") or over_limit
    claim_status = _status_for(queue, needs_review)
    decision = "manual_review" if over_limit else QUEUE_TO_DECISION[queue]
    peak = max(results, key=lambda a: a.score)
    bands = config.bands
    reason = (f"Score {final} = weighted rules {rule_final} + LLM {llm_extra} from {len(result.score.contributions)} "
              f"scored rule finding(s) (config {result.score.config_version}); score {final} maps to the '{queue}' queue.")
    if over_limit:
        reason += (f" The risk is low, but only claims below Rs {limit:,.0f} are auto-approved; this claim is "
                   f"Rs {claim.claimed_amount:,.0f}, so a person reviews it.")
    elif needs_review:
        reason += " Some checks were inconclusive, so a person should review the claim."
    orchestration = Orchestration(
        agents_run_in_parallel=_overlapped(traces), total_duration_ms=round(total_ms, 2),
        sum_of_agent_durations_ms=round(sum(t.duration_ms for t in traces), 2), traces=traces,
        weighted_score=final, peak_agent=peak.agent, peak_score=peak.score, peak_floor=0.0, final_score=final,
        score_rule="final = min(100, sum over agents of agent rule points x (weight x agents) + capped LLM points); "
                   "points = severity points x status multiplier over de-duplicated findings",
        thresholds={"manual_review_at": bands.review_at, "investigate_at": bands.investigate_at},
        decision_reason=reason, rule_score=rule_final, llm_score=llm_extra)
    progress("scoring", "done", {"score": final, "decision": decision})

    progress("summary", "running")
    summary = await llm.summarize(claim.claim_id, final, queue, results, use_llm)
    progress("summary", "done")
    if register is not None:
        with open_repos() as repos:
            repos.register_claim(claim, [d.sha256 for d in docs], is_test=(register == "test"),
                                 channel=DEMO_CHANNEL if register == "demo" else None)
    return FraudAssessment(claim_id=claim.claim_id, risk_score=final, decision=decision, agent_results=results,
                           orchestration=orchestration, summary=summary, recommended_queue=queue,
                           needs_human_review=needs_review, score_label=result.score.label,
                           claim_status=claim_status)
