import asyncio
import threading
import time
from uuid import uuid4

from app.core.finding import DetectionMethod, FactKey, FindingDraft, FindingStatus
from app.core.orchestrator import (Assessment, AssessmentContext, RunSettings, assess)
from app.core.risk_config import load_risk_config

CFG = load_risk_config()
FAST = RunSettings(timeout_s=0.2, retries=2)


def draft(check="c1", status=FindingStatus.POTENTIAL_ANOMALY, severity="medium", fact="f1",
          agent="Billing_Intelligence", method=DetectionMethod.RULE):
    return FindingDraft(use_case_id=1, check_id=check, agent=agent, category="x", severity=severity,
                        status=status, explanation="e", method=method, fact_key=FactKey(fact, ["s"]))


class Fake:
    requires = frozenset()

    def __init__(self, name, fn, agent="Billing_Intelligence"):
        self.name, self.agent, self._fn = name, agent, fn

    def run(self, ctx):
        return self._fn()


def ctx(caps=frozenset()):
    return AssessmentContext(claim_id=uuid4(), run_id=uuid4(), rule_version="v1", capabilities=caps)


def run(agents, settings=FAST):
    return asyncio.run(assess(ctx(), agents, CFG, None, settings=settings))


def test_agents_run_in_parallel():
    barrier = threading.Barrier(3, timeout=2)

    def wait():
        barrier.wait()  # only passes if all three run concurrently
        return [draft()]

    a = run([Fake(f"a{i}", wait) for i in range(3)], RunSettings(timeout_s=3, retries=0))
    assert all(e.state == "SUCCEEDED" for e in a.executions) and len(a.executions) == 3


def test_timeout_gives_inconclusive_and_records_each_attempt():
    a = run([Fake("slow", lambda: time.sleep(0.5) or [draft()])], RunSettings(timeout_s=0.05, retries=2))
    assert [e.state for e in a.executions] == ["TIMED_OUT"] * 3
    assert [e.attempt for e in a.executions] == [1, 2, 3]
    assert [f.status for f in a.findings] == [FindingStatus.INCONCLUSIVE]
    assert a.needs_human_review and a.claim_status == "NEEDS_HUMAN_REVIEW"


def test_retry_then_success():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return [draft()]

    a = run([Fake("flaky", flaky)])
    assert [e.state for e in a.executions] == ["FAILED", "SUCCEEDED"]
    assert not any(f.status is FindingStatus.INCONCLUSIVE for f in a.findings)


def test_agent_error_isolated():
    def bad():
        raise ValueError("x")

    a = run([Fake("bad", bad), Fake("ok", lambda: [draft(fact="other")])], RunSettings(1, 0))
    assert {f.status for f in a.findings} == {FindingStatus.INCONCLUSIVE, FindingStatus.POTENTIAL_ANOMALY}


def test_invalid_output_discarded_with_error_record():
    bad = {"check_id": "x", "severity": "huge"}
    a = run([Fake("inv", lambda: [draft(), bad])])
    assert len(a.executions) == 1
    e = a.executions[0]
    assert e.state == "INVALID_OUTPUT" and "invalid" in e.error
    checks = {f.check_id for f in a.findings}
    assert "c1" in checks and "x" not in checks
    assert any(f.status is FindingStatus.INCONCLUSIVE for f in a.findings)


def test_ai_status_capped_and_dedup_merges_agents():
    ai = draft("ai", FindingStatus.CONFIRMED_RULE_VIOLATION, fact="dup", method=DetectionMethod.AI,
               agent="Document_Forensics")
    rule = draft("rule", FindingStatus.CONFIRMED_RULE_VIOLATION, "high", fact="dup", agent="Duplicate_Detection")
    a = run([Fake("a", lambda: [ai], "Document_Forensics"), Fake("b", lambda: [rule], "Duplicate_Detection")])
    assert len(a.findings) == 1
    f = a.findings[0]
    assert f.contributing_checks == ["ai", "rule"]
    assert f.status is FindingStatus.CONFIRMED_RULE_VIOLATION and f.method is DetectionMethod.RULE
    assert a.score.score == CFG.severity_points.high * CFG.status_multiplier.CONFIRMED_RULE_VIOLATION
    capped = run([Fake("a", lambda: [ai])])
    assert capped.findings[0].status is FindingStatus.POTENTIAL_ANOMALY


def test_needs_human_review_rule():
    inc = draft("inc", FindingStatus.INCONCLUSIVE, fact="i")
    low = run([Fake("a", lambda: [inc])])
    assert low.recommended_queue == "low" and low.needs_human_review
    assert low.claim_status == "NEEDS_HUMAN_REVIEW"
    clean = run([Fake("a", lambda: [draft(status=FindingStatus.INFORMATIONAL)])])
    assert not clean.needs_human_review and clean.claim_status == "ASSESSED"
    high = run([Fake("a", lambda: [inc, draft("h1", FindingStatus.CONFIRMED_RULE_VIOLATION, "high", fact="h1"),
                                    draft("h2", FindingStatus.CONFIRMED_RULE_VIOLATION, "high", fact="h2")])])
    assert high.recommended_queue == "investigate"
    assert not high.needs_human_review and high.claim_status == "OPEN_INVESTIGATION"


def test_capability_filter_skips_agent():
    class Needs(Fake):
        requires = frozenset({"llm"})

    a = asyncio.run(assess(ctx(), [Needs("llmcheck", lambda: [draft()])], CFG, None, settings=FAST))
    assert a.skipped_agents == ("llmcheck",) and not a.executions


def test_result_has_no_decision_field():
    fields = set(Assessment.model_fields)
    assert {"recommended_queue", "needs_human_review"} <= fields
    assert not any(w in n for n in fields for w in ("decision", "deny", "denied", "reject", "outcome"))
    a = run([Fake("a", lambda: [])])
    assert a.claim_status in {"ASSESSED", "NEEDS_HUMAN_REVIEW", "OPEN_INVESTIGATION"}


def test_settings_from_env():
    s = RunSettings.from_env({"AGENT_TIMEOUT_S": "5", "AGENT_RETRIES": "3"})
    assert (s.timeout_s, s.retries) == (5.0, 3)


def test_legacy_runner_wraps_legacy_agent():
    from app.agents.provider_profile import ProviderProfileAgent
    from app.core.orchestrator import LegacyAgentRunner
    r = LegacyAgentRunner(ProviderProfileAgent())
    assert r.name == "provider_profile" and r.agent == "Provider_Intelligence"
