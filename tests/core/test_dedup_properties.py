from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.dedup import dedup_findings
from app.core.finding import SEVERITY_RANK, STATUS_RANK
from tests.strategies.findings import finding_lists


def _rank(f):
    return (STATUS_RANK[f.status], SEVERITY_RANK[f.severity])


# Feature: claims-fraud-detection-service, Property 4: Deduplication is idempotent, order independent and counts a fact once
# **Validates: Requirements 4.6, 5.4, 12.5**
@settings(max_examples=100)
@given(items=finding_lists(), data=st.data())
def test_dedup_properties(items, data):
    out = dedup_findings(items)

    # Idempotent
    assert dedup_findings(out) == out

    # Order independent
    shuffled = data.draw(st.permutations(items))
    assert dedup_findings(shuffled) == out

    # One output per distinct correlation key, sorted by key
    keys = [f.correlation_key for f in out]
    assert keys == sorted(set(f.correlation_key for f in items))

    for f in out:
        group = [g for g in items if g.correlation_key == f.correlation_key]
        # Winner has maximal (status, severity)
        assert _rank(f) == max(_rank(g) for g in group)
        # Winner is one of the group members
        assert f.finding_id in {g.finding_id for g in group}
        # Unions contain every member's contributions
        assert set(f.contributing_checks) >= {c for g in group for c in g.contributing_checks}
        assert set(f.contributing_sources) >= {s for g in group for s in g.contributing_sources}
        assert set(f.contributing_use_case_ids) >= {
            u for g in group for u in g.contributing_use_case_ids
        }
