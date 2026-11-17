"""Property 3: unscored statuses never change the score. Requirements 5.3."""
from hypothesis import given, settings, strategies as st

from app.core.finding import FindingStatus
from app.core.risk_config import load_risk_config
from app.core.scoring import score

from tests.strategies.finding_drafts import finding_drafts

CONFIG = load_risk_config()

_unscored = st.sampled_from(
    [FindingStatus.NOT_CHECKED, FindingStatus.INFORMATIONAL, FindingStatus.INCONCLUSIVE]
)


# Feature: claims-fraud-detection-service, Property 3: Unscored statuses never change the score
@settings(max_examples=100)
@given(
    base=st.lists(finding_drafts(), max_size=10),
    extra=st.lists(finding_drafts(status=_unscored), max_size=10),
)
def test_unscored_statuses_never_change_score(base, extra):
    """**Validates: Requirements 5.3**"""
    without = score(base, CONFIG)
    with_extra = score(base + extra, CONFIG)

    assert with_extra.score == without.score

    n = len(base)
    not_scored_idx = {ns.index for ns in with_extra.not_scored}
    for k, item in enumerate(extra):
        assert n + k in not_scored_idx
    for ns in with_extra.not_scored:
        if ns.index >= n:
            assert ns.status == extra[ns.index - n].status
    assert all(c.index < n for c in with_extra.contributions)
