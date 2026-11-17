from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.finding import DetectionMethod, FactKey, Finding, FindingDraft, FindingStatus
from app.core.risk_config import load_risk_config
from app.core.scoring import score

CFG = load_risk_config()
S = FindingStatus


def draft(status, severity, n=0, method=DetectionMethod.RULE):
    return FindingDraft(
        use_case_id=1,
        check_id=f"c{n}",
        agent="Billing_Intelligence",
        category="c",
        severity=severity,
        status=status,
        explanation="e",
        method=method,
        fact_key=FactKey("f", n),
    )


def test_empty_scores_zero():
    r = score([], CFG)
    assert r.score == 0 and r.contributions == () and r.not_scored == ()
    assert r.label == "Ordering signal, not a probability"
    assert r.config_version == CFG.version


@pytest.mark.parametrize(
    "status,severity,points",
    [
        (S.CONFIRMED_RULE_VIOLATION, "low", 10),
        (S.CONFIRMED_RULE_VIOLATION, "medium", 25),
        (S.CONFIRMED_RULE_VIOLATION, "high", 45),
        (S.POTENTIAL_ANOMALY, "low", 6),
        (S.POTENTIAL_ANOMALY, "medium", 15),
        (S.POTENTIAL_ANOMALY, "high", 27),
    ],
)
def test_single_contribution(status, severity, points):
    r = score([draft(status, severity)], CFG)
    assert r.score == points
    assert r.contributions[0].points == points


@pytest.mark.parametrize("status", [S.NOT_CHECKED, S.INFORMATIONAL, S.INCONCLUSIVE])
def test_unscored_statuses_listed_separately(status):
    r = score([draft(status, "high", 3)], CFG)
    assert r.score == 0
    assert r.contributions == ()
    assert [(n.index, n.status) for n in r.not_scored] == [(0, status)]


def test_sum_and_index_for_drafts():
    fs = [
        draft(S.CONFIRMED_RULE_VIOLATION, "medium", 1),
        draft(S.INFORMATIONAL, "high", 2),
        draft(S.POTENTIAL_ANOMALY, "low", 3),
    ]
    r = score(fs, CFG)
    assert r.score == 31.0
    assert [c.index for c in r.contributions] == [0, 2]
    assert all(c.finding_id is None for c in r.contributions)
    assert [n.index for n in r.not_scored] == [1]


def test_saturates_at_100():
    fs = [draft(S.CONFIRMED_RULE_VIOLATION, "high", i) for i in range(5)]
    assert score(fs, CFG).score == 100.0


def test_rounds_to_one_decimal():
    cfg = CFG.model_copy(
        update={"severity_points": CFG.severity_points.model_copy(update={"low": 10.04})}
    )
    assert score([draft(S.CONFIRMED_RULE_VIOLATION, "low")], cfg).score == 10.0


def test_finding_contributions_keyed_by_finding_id():
    d = draft(S.CONFIRMED_RULE_VIOLATION, "high")
    fid = UUID(int=7)
    f = Finding.from_draft(
        d,
        finding_id=fid,
        claim_id=uuid4(),
        run_id=uuid4(),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        rule_version="1",
    )
    r = score([f], CFG)
    assert r.contributions[0].finding_id == fid


def test_ai_confirmed_is_capped_before_scoring():
    d = draft(S.CONFIRMED_RULE_VIOLATION, "high", method=DetectionMethod.AI)
    assert score([d], CFG).score == 27.0


def test_result_is_frozen_and_input_not_mutated():
    fs = [draft(S.POTENTIAL_ANOMALY, "low")]
    r = score(fs, CFG)
    with pytest.raises(Exception):
        r.score = 1
    assert len(fs) == 1
