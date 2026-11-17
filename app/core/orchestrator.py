"""Core orchestrator: run agents in parallel, validate, dedup, score, route.

No database access and no web framework. The worker persists the returned ``Assessment``.
Requirements 4.1-4.8, 5.1.

The result has ``recommended_queue`` and ``needs_human_review`` only. There is no decision
field, so a denial or rejection cannot be represented (Req 4.8).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, Sequence, runtime_checkable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.dedup import dedup_findings
from app.core.finding import AgentName, DetectionMethod, FactKey, Finding, FindingDraft, FindingStatus
from app.core.risk_config import RiskConfig
from app.core.routing import Route, route
from app.core.scoring import ScoreResult, score

ClaimStatus = Literal["ASSESSED", "NEEDS_HUMAN_REVIEW", "OPEN_INVESTIGATION"]
ExecutionState = Literal["SUCCEEDED", "FAILED", "TIMED_OUT", "INVALID_OUTPUT"]

# Environment variable names for the run settings. Defaults apply only when unset.
ENV_TIMEOUT = "AGENT_TIMEOUT_S"
ENV_RETRIES = "AGENT_RETRIES"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRIES = 1


@dataclass(frozen=True)
class RunSettings:
    timeout_s: float
    retries: int  # extra attempts after the first

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "RunSettings":
        if env is None:
            from app.settings import get_settings  # core stays import-light; settings own the environment
            s = get_settings()
            return cls(timeout_s=s.agent_timeout_s, retries=max(0, s.agent_retries))
        e = env
        return cls(
            timeout_s=float(e.get(ENV_TIMEOUT) or DEFAULT_TIMEOUT_S),
            retries=max(0, int(e.get(ENV_RETRIES) or DEFAULT_RETRIES)),
        )


@dataclass(frozen=True)
class AssessmentContext:
    """Immutable input for one processing run. ``claim`` and ``documents`` are opaque to the core."""

    claim_id: UUID
    run_id: UUID
    rule_version: str
    claim: Any = None
    documents: Sequence[Any] = ()
    capabilities: frozenset[str] = frozenset()
    now: datetime | None = None


@runtime_checkable
class AgentRunner(Protocol):
    """Minimal agent protocol. ``run`` is blocking; the orchestrator runs it in a thread.

    It returns FindingDraft objects or dicts that should validate as FindingDraft.
    """

    name: str            # unique id used in execution records
    agent: AgentName     # attribution for INCONCLUSIVE findings
    requires: frozenset[str]

    def run(self, ctx: AssessmentContext) -> Sequence[Any]: ...


class AgentExecution(BaseModel):
    """One record per attempt (Req 4.3)."""

    model_config = ConfigDict(frozen=True)

    agent: str
    attempt: int
    state: ExecutionState
    started_at: datetime
    finished_at: datetime
    error: str | None = None
    finding_count: int = 0


class Assessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...]
    score: ScoreResult
    recommended_queue: Route
    needs_human_review: bool
    claim_status: ClaimStatus
    executions: tuple[AgentExecution, ...]
    skipped_agents: tuple[str, ...] = ()


class _AttemptError(Exception):
    def __init__(self, state: ExecutionState, message: str):
        super().__init__(message)
        self.state = state


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _inconclusive(runner: AgentRunner, reason: str) -> FindingDraft:
    return FindingDraft(
        use_case_id=0,
        check_id=f"{runner.name}.agent_failure",
        agent=runner.agent,
        category="agent_failure",
        severity="low",
        status=FindingStatus.INCONCLUSIVE,
        explanation=f"{runner.name} did not complete: {reason}",
        method=DetectionMethod.RULE,
        limitations=["An analysis module failed, so its checks did not complete."],
        next_action="Re-run the analysis or review the claim manually.",
        fact_key=FactKey("agent_failure", [runner.name]),
    )


def _validate(raw: Sequence[Any]) -> tuple[list[FindingDraft], list[str]]:
    """Validate each item against the FindingDraft schema. Returns (valid, error messages)."""
    valid: list[FindingDraft] = []
    errors: list[str] = []
    for i, item in enumerate(raw):
        try:
            data = item.model_dump() if isinstance(item, BaseModel) else item
            valid.append(FindingDraft.model_validate(data))
        except (ValidationError, TypeError, ValueError, AttributeError) as e:
            errors.append(f"item {i}: {type(e).__name__}: {str(e)[:200]}")
    return valid, errors


async def _attempt(runner: AgentRunner, ctx: AssessmentContext, timeout_s: float) -> Sequence[Any]:
    try:
        return await asyncio.wait_for(asyncio.to_thread(runner.run, ctx), timeout=timeout_s)
    except asyncio.TimeoutError:
        raise _AttemptError("TIMED_OUT", f"timed out after {timeout_s:g}s") from None
    except Exception as e:  # one failing agent must not sink the claim
        raise _AttemptError("FAILED", f"{type(e).__name__}: {e}") from e


async def _run_agent(
    runner: AgentRunner, ctx: AssessmentContext, settings: RunSettings
) -> tuple[list[FindingDraft], list[AgentExecution]]:
    executions: list[AgentExecution] = []
    last_error = "unknown"
    for attempt in range(1, settings.retries + 2):
        started = _utcnow()
        try:
            raw = await _attempt(runner, ctx, settings.timeout_s)
        except _AttemptError as e:
            last_error = str(e)
            executions.append(AgentExecution(agent=runner.name, attempt=attempt, state=e.state,
                                             started_at=started, finished_at=_utcnow(), error=last_error))
            continue
        valid, errors = _validate(list(raw or ()))
        if errors:
            # Invalid output is discarded and recorded; the agent yields INCONCLUSIVE (not retried).
            msg = f"{len(errors)} invalid finding(s) discarded: " + "; ".join(errors)
            executions.append(AgentExecution(agent=runner.name, attempt=attempt, state="INVALID_OUTPUT",
                                             started_at=started, finished_at=_utcnow(), error=msg,
                                             finding_count=len(valid)))
            return valid + [_inconclusive(runner, "returned invalid output")], executions
        executions.append(AgentExecution(agent=runner.name, attempt=attempt, state="SUCCEEDED",
                                         started_at=started, finished_at=_utcnow(), finding_count=len(valid)))
        return valid, executions
    return [_inconclusive(runner, last_error)], executions


def _status_for(queue: Route, needs_review: bool) -> ClaimStatus:
    if queue == "investigate":
        return "OPEN_INVESTIGATION"
    if queue == "manual_review" or needs_review:
        return "NEEDS_HUMAN_REVIEW"
    return "ASSESSED"


async def assess(
    ctx: AssessmentContext,
    registry: Sequence[AgentRunner],
    config: RiskConfig,
    adapters: Any = None,
    *,
    settings: RunSettings | None = None,
) -> Assessment:
    """Run applicable agents in parallel and return the scored, routed assessment.

    ``adapters`` is reserved for agents that need adapter access; the core does not use it.
    ``settings`` defaults to AGENT_TIMEOUT_S / AGENT_RETRIES from the environment.
    """
    settings = settings or RunSettings.from_env()
    applicable = [r for r in registry if set(getattr(r, "requires", ())) <= set(ctx.capabilities)]
    skipped = tuple(r.name for r in registry if r not in applicable)

    results = await asyncio.gather(*(_run_agent(r, ctx, settings) for r in applicable))
    drafts = [d for ds, _ in results for d in ds]
    executions = tuple(e for _, es in results for e in es)

    created_at = ctx.now or _utcnow()
    findings = [
        Finding.from_draft(d, finding_id=uuid4(), claim_id=ctx.claim_id, run_id=ctx.run_id,
                           created_at=created_at, rule_version=ctx.rule_version)
        for d in drafts
    ]
    merged = dedup_findings(findings)
    result = score(merged, config)
    queue = route(result.score, config.bands)
    needs_review = queue == "low" and any(f.status is FindingStatus.INCONCLUSIVE for f in merged)
    return Assessment(
        findings=tuple(merged), score=result, recommended_queue=queue,
        needs_human_review=needs_review, claim_status=_status_for(queue, needs_review),
        executions=executions, skipped_agents=skipped,
    )


@dataclass
class LegacyAgentRunner:
    """Wrap a legacy agent (``async analyze(claim, docs)``) as an AgentRunner.

    ctx.claim is the legacy Claim and ctx.documents the legacy DocumentInfo list.
    """

    legacy: Any
    agent: AgentName = "Operational_Intelligence"
    requires: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        from app.core.legacy_adapter import _AGENT_BY_LEGACY
        self.name: str = self.legacy.name
        self.agent = _AGENT_BY_LEGACY.get(self.name, self.agent)

    def run(self, ctx: AssessmentContext) -> list[FindingDraft]:
        from app.core.legacy_adapter import adapt_findings, context_from_claim
        docs = list(ctx.documents)
        # Own event loop per thread, as the legacy orchestrator did.
        result = asyncio.run(self.legacy.analyze(ctx.claim, docs))
        lctx = context_from_claim(ctx.claim, docs, agent_name=self.name)
        return adapt_findings(result.findings, lctx)
