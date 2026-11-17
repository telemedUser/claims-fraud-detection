import asyncio
from uuid import uuid4

from hypothesis import given, settings, strategies as st

from app.core.orchestrator import Assessment, AssessmentContext, RunSettings, assess
from app.core.risk_config import load_risk_config
from tests.strategies.finding_drafts import finding_drafts

CFG = load_risk_config()
FAST = RunSettings(timeout_s=1, retries=0)
FORBIDDEN = ("deny", "denied", "reject", "rejected")


class Fake:
    requires = frozenset()

    def __init__(self, name, fn):
        self.name, self.agent, self._fn = name, "Billing_Intelligence", fn

    def run(self, ctx):
        return self._fn()


def _raise():
    raise RuntimeError("controlled failure")


agent_behaviour = st.one_of(
    st.lists(finding_drafts(), max_size=5).map(lambda ds: (lambda: ds)),
    st.just(_raise),
    st.just(lambda: [{"check_id": "x", "severity": "huge"}]),
    st.just(lambda: "not a list"),
)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _strings(v)


# Feature: claims-fraud-detection-service, Property 9: Orchestrator never emits deny or reject
# **Validates: Requirements 4.8**
@settings(max_examples=100, deadline=None)
@given(behaviours=st.lists(agent_behaviour, max_size=4))
def test_orchestrator_never_emits_deny_or_reject(behaviours):
    agents = [Fake(f"a{i}", fn) for i, fn in enumerate(behaviours)]
    ctx = AssessmentContext(claim_id=uuid4(), run_id=uuid4(), rule_version="v1", capabilities=frozenset())
    a = asyncio.run(assess(ctx, agents, CFG, None, settings=FAST))

    assert a.claim_status in {"ASSESSED", "NEEDS_HUMAN_REVIEW", "OPEN_INVESTIGATION"}
    assert a.recommended_queue in {"low", "manual_review", "investigate"}
    assert not any(w in n.lower() for n in Assessment.model_fields for w in FORBIDDEN)
    dumped = a.model_dump(mode="json")
    for s in _strings(dumped):
        assert not any(w in s.lower() for w in FORBIDDEN), s
