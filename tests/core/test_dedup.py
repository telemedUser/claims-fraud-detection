from datetime import datetime, timezone
from itertools import permutations
from uuid import UUID, uuid4

from app.core.dedup import dedup_findings
from app.core.finding import (
    DetectionMethod,
    FactKey,
    Finding,
    FindingDraft,
    FindingStatus,
)

RUN = uuid4()
CLAIM = uuid4()


def mk(check_id, use_case_id, status, severity, fid, fact="x", source="s"):
    draft = FindingDraft(
        use_case_id=use_case_id,
        check_id=check_id,
        agent="Duplicate_Detection",
        category="c",
        severity=severity,
        status=status,
        explanation="e",
        source_field=source,
        method=DetectionMethod.RULE,
        fact_key=FactKey(fact, "subj", ("v",)),
    )
    return Finding.from_draft(
        draft,
        finding_id=UUID(int=fid),
        claim_id=CLAIM,
        run_id=RUN,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        rule_version="1",
    )


def test_empty():
    assert dedup_findings([]) == []


def test_distinct_keys_kept():
    out = dedup_findings(
        [
            mk("a", 1, FindingStatus.POTENTIAL_ANOMALY, "low", 1, fact="x"),
            mk("b", 2, FindingStatus.POTENTIAL_ANOMALY, "low", 2, fact="y"),
        ]
    )
    assert len(out) == 2


def test_highest_status_wins_over_severity_and_unions_sorted():
    a = mk("zz", 9, FindingStatus.POTENTIAL_ANOMALY, "high", 1, source="s2")
    b = mk("aa", 3, FindingStatus.CONFIRMED_RULE_VIOLATION, "low", 2, source="s1")
    (out,) = dedup_findings([a, b])
    assert out.check_id == "aa"
    assert out.status is FindingStatus.CONFIRMED_RULE_VIOLATION
    assert out.contributing_checks == ["aa", "zz"]
    assert out.contributing_sources == ["s1", "s2"]
    assert out.contributing_use_case_ids == [3, 9]


def test_severity_breaks_status_tie():
    a = mk("a", 1, FindingStatus.POTENTIAL_ANOMALY, "low", 1)
    b = mk("b", 2, FindingStatus.POTENTIAL_ANOMALY, "high", 2)
    (out,) = dedup_findings([a, b])
    assert out.severity == "high"


def test_full_tie_is_order_independent():
    fs = [
        mk("c", 1, FindingStatus.POTENTIAL_ANOMALY, "low", 3),
        mk("a", 2, FindingStatus.POTENTIAL_ANOMALY, "low", 2),
        mk("b", 3, FindingStatus.POTENTIAL_ANOMALY, "low", 1),
    ]
    results = {dedup_findings(list(p))[0].model_dump_json() for p in permutations(fs)}
    assert len(results) == 1
    assert dedup_findings(fs)[0].check_id == "a"


def test_inputs_not_mutated():
    a = mk("a", 1, FindingStatus.POTENTIAL_ANOMALY, "low", 1)
    b = mk("b", 2, FindingStatus.CONFIRMED_RULE_VIOLATION, "low", 2)
    dedup_findings([a, b])
    assert a.contributing_checks == ["a"]
    assert b.contributing_checks == ["b"]
