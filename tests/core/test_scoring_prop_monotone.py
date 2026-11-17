from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.dedup import dedup_findings
from app.core.finding import SEVERITY_RANK, STATUS_RANK
from app.core.risk_config import load_risk_config
from app.core.scoring import score
from tests.strategies.findings import finding_lists, findings

CONFIG = load_risk_config()


# Feature: claims-fraud-detection-service, Property 2: Score is monotone in added evidence
# **Validates: Requirements 5.1, 5.4**
@settings(max_examples=100)
@given(items=finding_lists(), extra=findings())
def test_adding_a_finding_never_lowers_score(items, extra):
    before = score(items, CONFIG).score
    after = score([*items, extra], CONFIG).score
    assert after >= before


# Feature: claims-fraud-detection-service, Property 2: Score is monotone in added evidence
# **Validates: Requirements 5.1, 5.4**
@settings(max_examples=100)
@given(items=finding_lists().filter(bool), data=st.data())
def test_duplicate_of_lower_rank_does_not_change_deduped_score(items, data):
    base = data.draw(st.sampled_from(items))
    rank = (STATUS_RANK[base.status], SEVERITY_RANK[base.severity])
    status = data.draw(
        st.sampled_from([s for s in STATUS_RANK if STATUS_RANK[s] <= rank[0]])
    )
    severity = data.draw(
        st.sampled_from([s for s in SEVERITY_RANK if SEVERITY_RANK[s] <= rank[1]])
    )
    dup = base.model_copy(
        update={
            "finding_id": data.draw(st.uuids(version=4)),
            "status": status,
            "severity": severity,
        }
    )
    assert dup.correlation_key == base.correlation_key
    # The existing key's best rank is at least base's rank, so dup never wins.
    best = max((STATUS_RANK[f.status], SEVERITY_RANK[f.severity])
               for f in items if f.correlation_key == base.correlation_key)
    if (STATUS_RANK[status], SEVERITY_RANK[severity]) > best:
        return
    before = score(dedup_findings(items), CONFIG).score
    after = score(dedup_findings([*items, dup]), CONFIG).score
    assert after == before
