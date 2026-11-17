import asyncio
from uuid import uuid4

from hypothesis import given, settings, strategies as st

from app.core.finding import FindingStatus
from app.core.orchestrator import AssessmentContext, RunSettings, assess
from app.core.risk_config import load_risk_config
from tests.strategies.finding_drafts import finding_drafts

CFG = load_risk_config()
SETTINGS = RunSettings(timeout_s=1, retries=0)


class Fake:
    requires = frozenset()

    def __init__(self, name, fn, agent="Billing_Intelligence"):
        self.name, self.agent, self._fn = name, agent, fn

    def run(self, ctx):
        return self._fn()


def _make_agent(i, spec):
    drafts, fails = spec

    def fn():
        if fails:
            raise RuntimeError("boom")
        return drafts

    return Fake(f"agent{i}", fn)


agent_specs = st.tuples(st.lists(finding_drafts(), max_size=4), st.booleans())


# Feature: claims-fraud-detection-service, Property 10: Inconclusive findings on a low band force human review
# **Validates: Requirements 4.7**
@settings(max_examples=100, deadline=None)
@given(specs=st.lists(agent_specs, max_size=4))
def test_inconclusive_on_low_band_forces_human_review(specs):
    agents = [_make_agent(i, s) for i, s in enumerate(specs)]
    ctx = AssessmentContext(claim_id=uuid4(), run_id=uuid4(), rule_version="v1")
    a = asyncio.run(assess(ctx, agents, CFG, None, settings=SETTINGS))

    has_inconclusive = any(f.status is FindingStatus.INCONCLUSIVE for f in a.findings)
    assert a.needs_human_review == (a.recommended_queue == "low" and has_inconclusive)

    if a.recommended_queue == "investigate":
        expected = "OPEN_INVESTIGATION"
    elif a.recommended_queue == "manual_review" or a.needs_human_review:
        expected = "NEEDS_HUMAN_REVIEW"
    else:
        expected = "ASSESSED"
    assert a.claim_status == expected
