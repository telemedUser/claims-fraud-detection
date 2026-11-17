from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from app.core.finding import (
    DetectionMethod,
    FactKey,
    Finding,
    FindingDraft,
    FindingStatus,
    correlation_key,
    normalise_status,
)


def draft(**kw):
    base = dict(
        use_case_id=1, check_id="POL-DATE-WINDOW", agent="Policy_Eligibility", category="policy",
        severity="high", status=FindingStatus.CONFIRMED_RULE_VIOLATION, explanation="x",
        method=DetectionMethod.RULE, fact_key=FactKey("claim_date_window", {"c": 1}, {"d": "2024"}),
    )
    base.update(kw)
    return FindingDraft(**base)


def test_key_is_order_independent_and_sha256():
    a = correlation_key(FactKey("t", {"a": 1, "b": 2}, {"x": [1]}))
    b = correlation_key(FactKey("t", {"b": 2, "a": 1}, {"x": [1]}))
    assert a == b and len(a) == 64
    assert a != correlation_key(FactKey("t", {"a": 1, "b": 2}, {"x": [2]}))


@given(st.dictionaries(st.text(max_size=5), st.integers(), max_size=5))
def test_key_stable_under_reordering(d):
    rev = dict(reversed(list(d.items())))
    assert correlation_key(FactKey("t", d, {})) == correlation_key(FactKey("t", rev, {}))


@pytest.mark.parametrize("method", [DetectionMethod.AI, DetectionMethod.ML])
def test_ai_ml_capped(method):
    assert normalise_status(FindingStatus.CONFIRMED_RULE_VIOLATION, method) is FindingStatus.POTENTIAL_ANOMALY
    assert draft(method=method).status is FindingStatus.POTENTIAL_ANOMALY


def test_rule_not_capped_and_lower_statuses_kept():
    assert draft().status is FindingStatus.CONFIRMED_RULE_VIOLATION
    assert draft(method=DetectionMethod.AI, status=FindingStatus.INCONCLUSIVE).status is FindingStatus.INCONCLUSIVE


def test_not_checked_fact_key():
    d = draft(status=FindingStatus.NOT_CHECKED)
    assert d.fact_key.fact_type == "not_checked"
    assert d.fact_key.subject == "POL-DATE-WINDOW"
    # accepts the literal tuple form too
    d2 = draft(status=FindingStatus.NOT_CHECKED, fact_key=("not_checked", "POL-DATE-WINDOW"))
    assert correlation_key(d2.fact_key) == correlation_key(d.fact_key)


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        draft(status="MAYBE")


def test_finding_immutable_and_keyed():
    d = draft()
    f = Finding.from_draft(
        d, finding_id=uuid4(), claim_id=uuid4(), run_id=uuid4(),
        created_at=datetime.now(timezone.utc), rule_version="v1",
    )
    assert f.correlation_key == correlation_key(d.fact_key)
    assert f.contributing_checks == ["POL-DATE-WINDOW"]
    with pytest.raises(ValidationError):
        f.severity = "low"
