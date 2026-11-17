"""Property 1: score is bounded, deterministic and explained. Requirements 5.1, 5.2, 5.5."""
from hypothesis import given, settings, strategies as st

from app.core.risk_config import load_risk_config
from app.core.scoring import score

from tests.strategies.finding_drafts import finding_drafts
from tests.strategies.findings import finding_lists

CONFIG = load_risk_config()

_inputs = st.one_of(finding_lists(), st.lists(finding_drafts(), max_size=12))


# Feature: claims-fraud-detection-service, Property 1: Score is bounded, deterministic and explained
@settings(max_examples=100)
@given(items=_inputs)
def test_score_is_bounded_deterministic_and_explained(items):
    """**Validates: Requirements 5.1, 5.2, 5.5**"""
    result = score(items, CONFIG)

    assert 0 <= result.score <= 100
    assert score(items, CONFIG) == result

    total = sum(c.points for c in result.contributions)
    assert result.score == min(100.0, round(total, 1))

    scored = set(CONFIG.scored_statuses)
    expected = [i for i, f in enumerate(items) if f.status in scored]
    assert sorted(c.index for c in result.contributions) == expected
    for c in result.contributions:
        f = items[c.index]
        assert c.check_id == f.check_id
        assert c.severity == f.severity
        assert c.status == f.status
        assert getattr(f, "finding_id", None) == c.finding_id

    assert result.config_version == CONFIG.version
    assert result.label == CONFIG.label
