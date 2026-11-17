from hypothesis import given, settings

from app.core.finding import DetectionMethod, Finding, FindingStatus, normalise_status
from tests.strategies.finding_drafts import (
    capped_methods,
    finding_drafts,
    finding_kwargs,
    methods,
    statuses,
    uncapped_methods,
)

# Feature: claims-fraud-detection-service, Property 7: AI and ML findings are capped
# **Validates: Requirements 3.2, 3.3, 10.6**


@settings(max_examples=100)
@given(finding_drafts(method=capped_methods))
def test_ai_ml_drafts_never_confirmed(draft):
    assert draft.status in {
        FindingStatus.POTENTIAL_ANOMALY,
        FindingStatus.INFORMATIONAL,
        FindingStatus.NOT_CHECKED,
        FindingStatus.INCONCLUSIVE,
    }
    assert draft.status is not FindingStatus.CONFIRMED_RULE_VIOLATION


@settings(max_examples=100)
@given(statuses, uncapped_methods)
def test_non_ai_methods_keep_status(status, method):
    assert normalise_status(status, method) is status


@settings(max_examples=100)
@given(statuses, methods)
def test_normalise_yields_single_status_and_caps(status, method):
    result = normalise_status(status, method)
    assert isinstance(result, FindingStatus)
    if method in (DetectionMethod.AI, DetectionMethod.ML):
        assert result is not FindingStatus.CONFIRMED_RULE_VIOLATION
        if status is FindingStatus.CONFIRMED_RULE_VIOLATION:
            assert result is FindingStatus.POTENTIAL_ANOMALY
        else:
            assert result is status


@settings(max_examples=100)
@given(finding_drafts())
def test_draft_has_one_status_and_from_draft_preserves(draft):
    assert isinstance(draft.status, FindingStatus)
    assert draft.status is normalise_status(draft.status, draft.method)
    finding = Finding.from_draft(draft, **finding_kwargs())
    assert finding.status is draft.status
    if finding.method in (DetectionMethod.AI, DetectionMethod.ML):
        assert finding.status is not FindingStatus.CONFIRMED_RULE_VIOLATION
